"""A private, single-threaded PTY broker per session. No public TCP listener."""
import errno
import fcntl
import json
import os
from pathlib import Path
import pty
import selectors
import shutil
import signal
import socket
import struct
import subprocess
import termios
import time
import uuid

from .common import (MAX_FRAME, REPLAY_BYTES, decode, encode, frame, launch_prefix,
                     read_json, request, session_dir, socket_path, state_root, write_json)


def agent_command(agent, executable=None, resume=None, background=None):
    binary = executable or agent
    resolved = shutil.which(binary)
    if not resolved:
        raise ValueError("Executable not found: %s (check the host PATH or --executable)" % binary)
    command = [resolved]
    if background:
        if agent != "claude":
            raise ValueError("--background-id is only supported for Claude Code")
        command += ["attach", background]
    elif resume:
        command += ["resume", resume] if agent == "codex" else ["--resume", resume]
    return command


def create(agent, cwd, name=None, executable=None, resume=None, background=None):
    command = agent_command(agent, executable, resume, background)
    cwd = str(Path(cwd).expanduser().resolve(strict=True))
    if not Path(cwd).is_dir():
        raise ValueError("Working directory must be a directory on the host")
    session = uuid.uuid4().hex[:12]
    directory = session_dir(session)
    socket_path(directory)  # Fail before spawning if the platform path limit is exceeded.
    directory.mkdir(mode=0o700)
    meta = dict(id=session, agent=agent, name=name or agent, cwd=cwd,
                command=command, status="starting", created_at=time.time(),
                background_id=background, resume_id=resume)
    write_json(directory / "session.json", meta)
    with open(directory / "broker.log", "ab", buffering=0) as log:
        os.chmod(directory / "broker.log", 0o600)
        process = subprocess.Popen(launch_prefix() + ["_serve", session],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   start_new_session=True, close_fds=True)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            return request(session, {"op": "info"})["session"]
        except (OSError, ValueError):
            current = read_json(directory / "session.json")
            if current["status"] == "exited" or process.poll() is not None:
                raise ValueError("Agent failed to start; inspect `logs %s` and %s" % (session, directory / "broker.log"))
            time.sleep(0.05)
    raise ValueError("Session startup timed out (%s); inspect `list` before retrying" % session)


def sessions():
    result = []
    for path in state_root().glob("*/session.json"):
        try:
            meta = read_json(path)
            if meta["status"] in ("running", "starting", "stopping"):
                try:
                    meta = request(meta["id"], {"op": "info"}, timeout=0.5)["session"]
                except (OSError, ValueError):
                    meta["status"] = "unreachable"
            result.append(meta)
        except (OSError, ValueError, KeyError):
            continue
    return sorted(result, key=lambda item: item["created_at"])


def logs(session):
    try:
        return decode(request(session, {"op": "logs"})["data"])
    except (ConnectionRefusedError, FileNotFoundError):
        directory = session_dir(session)
        if not (directory / "session.json").exists():
            raise ValueError("Session not found: " + session)
        tail = directory / "output.tail"
        return tail.read_bytes() if tail.exists() else b""


def resize(fd, rows, cols):
    if not isinstance(rows, int) or not isinstance(cols, int) or not (1 <= rows <= 1000 and 1 <= cols <= 1000):
        raise ValueError("Terminal dimensions must be integers between 1 and 1000")
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


class Peer:
    def __init__(self, conn):
        self.conn = conn
        self.incoming = bytearray()
        self.outgoing = bytearray()
        self.attached = False
        self.read_only = True
        self.closing = False


class Broker:
    def __init__(self, session):
        self.directory = session_dir(session)
        self.meta = read_json(self.directory / "session.json")
        self.selector = selectors.DefaultSelector()
        self.peers = {}
        self.owner = None
        self.tail = bytearray()
        self.pending_input = bytearray()
        self.offset = 0
        self.child_status = None
        self.pty_eof = False
        self.stop_deadline = None
        self.finish_deadline = None
        self.last_checkpoint = time.monotonic()

    def drop(self, peer):
        if self.owner is peer:
            self.owner = None
        self.peers.pop(peer.conn.fileno(), None)
        try:
            self.selector.unregister(peer.conn)
        except KeyError:
            pass
        peer.conn.close()

    def queue(self, peer, value):
        if peer.conn.fileno() < 0:
            return
        packet = frame(value)
        if len(peer.outgoing) + len(packet) > MAX_FRAME:
            # A slow client must never block the PTY or unboundedly consume memory.
            self.drop(peer)
            return
        peer.outgoing.extend(packet)
        self.selector.modify(peer.conn, selectors.EVENT_READ | selectors.EVENT_WRITE, peer)

    def info(self):
        return dict(self.meta, attached=sum(p.attached for p in self.peers.values()),
                    controller=self.owner is not None)

    def handle(self, peer, message):
        if not isinstance(message, dict):
            raise ValueError("Expected an object")
        op = message.get("op")
        if op == "info":
            self.queue(peer, {"session": self.info()})
        elif op == "logs":
            self.queue(peer, {"data": encode(self.tail), "offset": self.offset})
        elif op == "attach":
            read_only = message.get("read_only", False)
            if not isinstance(read_only, bool):
                raise ValueError("read_only must be boolean")
            if not read_only and self.owner not in (None, peer):
                raise ValueError("Session already has a controller; use --read-only or detach it first")
            if peer.attached:
                raise ValueError("Already attached")
            if not read_only:
                resize(self.master, message.get("rows", 24), message.get("cols", 80))
                self.owner = peer
            peer.attached, peer.read_only = True, read_only
            self.queue(peer, {"event": "attached", "session": self.info(), "read_only": read_only})
            self.queue(peer, {"event": "output", "data": encode(self.tail),
                              "offset": self.offset, "replay": True})
        elif op in ("input", "resize"):
            if peer is not self.owner:
                raise ValueError("Only the attached controller can send input or resize")
            if op == "resize":
                resize(self.master, message["rows"], message["cols"])
            else:
                data = decode(message["data"])
                if len(self.pending_input) + len(data) > MAX_FRAME:
                    raise ValueError("Input queue is full")
                self.pending_input.extend(data)
                self.update_master()
        elif op == "send":
            if self.owner:
                raise ValueError("Detach the active controller before using send")
            data = decode(message["data"])
            if len(self.pending_input) + len(data) > MAX_FRAME:
                raise ValueError("Input queue is full")
            self.pending_input.extend(data)
            self.update_master()
            self.queue(peer, {"ok": True})
        elif op == "stop":
            self.stop()
            self.queue(peer, {"ok": True})
        else:
            raise ValueError("Unknown operation: %s" % op)

    def update_master(self):
        if not self.pty_eof:
            self.selector.modify(self.master, selectors.EVENT_READ |
                                 (selectors.EVENT_WRITE if self.pending_input else 0), "pty")

    def signal_child(self, sig):
        if self.child_status is None:
            try:
                os.killpg(self.pid, sig)
            except ProcessLookupError:
                pass

    def stop(self):
        if self.stop_deadline is None:
            self.meta["status"] = "stopping"
            self.signal_child(signal.SIGTERM)
            self.stop_deadline = time.monotonic() + 3

    def checkpoint(self):
        path = self.directory / "output.tail"
        temporary = self.directory / "output.tmp"
        with open(temporary, "wb") as file:
            os.chmod(temporary, 0o600)
            file.write(self.tail)
        os.replace(temporary, path)
        self.last_checkpoint = time.monotonic()

    def read_pty(self):
        try:
            data = os.read(self.master, 65536)
        except OSError as exc:
            if exc.errno != errno.EIO:
                raise
            data = b""
        if not data:
            self.pty_eof = True
            self.selector.unregister(self.master)
            return
        self.offset += len(data)
        self.tail.extend(data)
        del self.tail[:-REPLAY_BYTES]
        for peer in list(self.peers.values()):
            if peer.attached:
                self.queue(peer, {"event": "output", "data": encode(data), "offset": self.offset})

    def peer_ready(self, peer, events):
        try:
            if events & selectors.EVENT_READ and not peer.closing:
                data = peer.conn.recv(65536)
                if not data:
                    self.drop(peer)
                    return
                peer.incoming.extend(data)
                if len(peer.incoming) > MAX_FRAME:
                    self.drop(peer)
                    return
                while b"\n" in peer.incoming and peer.conn.fileno() >= 0:
                    line, _, rest = peer.incoming.partition(b"\n")
                    peer.incoming = bytearray(rest)
                    try:
                        self.handle(peer, json.loads(line))
                    except (ValueError, KeyError, TypeError, OSError) as exc:
                        self.queue(peer, {"error": str(exc)})
            if events & selectors.EVENT_WRITE and peer.conn.fileno() >= 0:
                sent = peer.conn.send(peer.outgoing)
                del peer.outgoing[:sent]
                if not peer.outgoing:
                    if peer.closing:
                        self.drop(peer)
                    else:
                        self.selector.modify(peer.conn, selectors.EVENT_READ, peer)
        except (ConnectionError, BrokenPipeError):
            self.drop(peer)
        except BlockingIOError:
            pass

    def run(self):
        os.umask(0o077)
        # forkpty supplies a controlling terminal, needed by both interactive CLIs.
        self.pid, self.master = pty.fork()
        if self.pid == 0:
            try:
                os.chdir(self.meta["cwd"])
                os.environ.setdefault("TERM", "xterm-256color")
                os.execvpe(self.meta["command"][0], self.meta["command"], os.environ)
            except BaseException as exc:
                os.write(2, ("macrelay: " + str(exc) + "\n").encode())
                os._exit(127)
        try:
            resize(self.master, 24, 80)
            os.set_blocking(self.master, False)
            self.listener = socket.socket(socket.AF_UNIX)
            self.listener.bind(socket_path(self.directory))
            os.chmod(socket_path(self.directory), 0o600)
            self.listener.listen(16)
            self.listener.setblocking(False)
            self.selector.register(self.listener, selectors.EVENT_READ, "listener")
            self.selector.register(self.master, selectors.EVENT_READ, "pty")
            self.meta.update(status="running", pid=self.pid, broker_pid=os.getpid())
            write_json(self.directory / "session.json", self.meta)
            signal.signal(signal.SIGTERM, lambda *_: self.stop())
            signal.signal(signal.SIGINT, lambda *_: self.stop())
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
            self.loop()
        finally:
            self.signal_child(signal.SIGKILL)
            if self.child_status is None:
                _, self.child_status = os.waitpid(self.pid, 0)
            self.meta.update(status="exited", exit_code=os.waitstatus_to_exitcode(self.child_status),
                             ended_at=time.time())
            self.checkpoint()
            write_json(self.directory / "session.json", self.meta)
            for peer in list(self.peers.values()):
                self.drop(peer)
            self.selector.close()
            if hasattr(self, "listener"):
                self.listener.close()
            os.close(self.master)
            Path(socket_path(self.directory)).unlink(missing_ok=True)

    def loop(self):
        while True:
            for key, events in self.selector.select(0.1):
                if key.data == "listener":
                    conn, _ = self.listener.accept()
                    conn.setblocking(False)
                    if len(self.peers) >= 32 or self.finish_deadline:
                        conn.close()
                        continue
                    peer = Peer(conn)
                    self.peers[conn.fileno()] = peer
                    self.selector.register(conn, selectors.EVENT_READ, peer)
                elif key.data == "pty":
                    if events & selectors.EVENT_READ:
                        self.read_pty()
                    if events & selectors.EVENT_WRITE and self.pending_input and not self.pty_eof:
                        try:
                            sent = os.write(self.master, self.pending_input)
                            del self.pending_input[:sent]
                            self.update_master()
                        except BlockingIOError:
                            pass
                else:
                    self.peer_ready(key.data, events)
            if self.child_status is None:
                pid, status = os.waitpid(self.pid, os.WNOHANG)
                if pid:
                    self.child_status = status
            now = time.monotonic()
            if self.stop_deadline and now >= self.stop_deadline:
                self.signal_child(signal.SIGKILL)
            if now - self.last_checkpoint > 2:
                self.checkpoint()
            if self.child_status is not None and not self.finish_deadline:
                # Drain output already queued on the terminal before announcing exit.
                while not self.pty_eof:
                    try:
                        self.read_pty()
                    except BlockingIOError:
                        break
                self.finish_deadline = now + 1
                for peer in list(self.peers.values()):
                    if peer.attached:
                        self.queue(peer, {"event": "exit", "code": os.waitstatus_to_exitcode(self.child_status)})
                    peer.closing = True
            if self.finish_deadline and (not self.peers or now >= self.finish_deadline):
                return
