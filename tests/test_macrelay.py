import json
import os
from pathlib import Path
import pty
import select
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from unittest import mock

from macrelay.common import decode, encode, frame, request, session_dir
from macrelay.host import agent_command
from macrelay.transport import remote_command, ssh_prefix

ROOT = Path(__file__).resolve().parents[1]


def eventually(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.03)
    raise AssertionError("Condition did not become true")


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mr-", dir="/tmp")
        self.root = Path(self.temp.name)
        self.patch = mock.patch.dict(os.environ, {"MACRELAY_HOME": str(self.root / "state")})
        self.patch.start()
        self.sessions = []
        self.agent = self.root / "fake-agent"
        self.agent.write_text("""#!/usr/bin/env python3
import fcntl, os, signal, struct, sys, termios
if '--version' in sys.argv:
    print('fixture 1.0')
    sys.exit(0)
signal.signal(signal.SIGINT, lambda *_: print('INTERRUPTED', flush=True))
print('READY tty=' + str(os.isatty(0)), flush=True)
for line in sys.stdin:
    line = line.strip()
    if line == 'exit':
        print('GOODBYE', flush=True)
        break
    if line == 'size':
        size = struct.unpack('HHHH', fcntl.ioctl(0, termios.TIOCGWINSZ, b'\\0' * 8))
        print('SIZE=%sx%s' % size[:2], flush=True)
    elif line == 'flood':
        print('X' * 400000, flush=True)
    elif line == 'ignore-term':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        print('IGNORING', flush=True)
    else:
        print('ANSWER:' + line, flush=True)
""")
        self.agent.chmod(0o700)

    def tearDown(self):
        for session in self.sessions:
            try:
                request(session, {"op": "stop"}, timeout=0.5)
            except (OSError, ValueError):
                pass
        for session in self.sessions:
            try:
                eventually(lambda: not (session_dir(session) / "io.sock").exists(), timeout=5)
            except AssertionError:
                pass
        self.patch.stop()
        self.temp.cleanup()

    def cli(self, *args, check=True):
        return subprocess.run([sys.executable, str(ROOT / "run.py"), *args],
                              capture_output=True, text=True, check=check, timeout=12)

    def start(self, prefix=()):
        result = self.cli(*prefix, "start", "claude", "--cwd", str(self.root),
                          "--executable", str(self.agent))
        session = json.loads(result.stdout)["id"]
        self.sessions.append(session)
        eventually(lambda: "READY" in self.cli(*prefix, "logs", session).stdout)
        return session

    def connect(self, session, **options):
        conn = socket.socket(socket.AF_UNIX)
        conn.settimeout(3)
        conn.connect(str(session_dir(session) / "io.sock"))
        stream = conn.makefile("rb")
        conn.sendall(frame(dict(op="attach", **options)))
        return conn, stream

    def test_disconnect_replay_and_exclusive_controller(self):
        session = self.start()
        conn, stream = self.connect(session, rows=40, cols=120)
        self.assertEqual(json.loads(stream.readline())["event"], "attached")
        self.assertIn(b"READY tty=True", decode(json.loads(stream.readline())["data"]))
        other, other_stream = self.connect(session)
        self.assertIn("controller", json.loads(other_stream.readline())["error"])
        other_stream.close()
        other.close()
        viewer, view_stream = self.connect(session, read_only=True)
        self.assertTrue(json.loads(view_stream.readline())["read_only"])
        view_stream.readline()
        viewer.sendall(frame({"op": "input", "data": encode(b"bad\r")}))
        self.assertIn("controller", json.loads(view_stream.readline())["error"])
        conn.sendall(frame({"op": "input", "data": encode(b"size\r")}))
        eventually(lambda: b"SIZE=40x120" in decode(request(session, {"op": "logs"})["data"]))
        stream.close()
        conn.close()
        eventually(lambda: not request(session, {"op": "info"})["session"]["controller"])
        self.cli("send", session, "after disconnect")
        eventually(lambda: "ANSWER:after disconnect" in self.cli("logs", session).stdout)
        view_stream.close()
        viewer.close()
        again, again_stream = self.connect(session)
        again_stream.readline()
        self.assertIn(b"ANSWER:after disconnect", decode(json.loads(again_stream.readline())["data"]))
        again_stream.close()
        again.close()

    def test_exit_retains_tail_and_bounded_replay(self):
        session = self.start()
        self.cli("send", session, "flood")
        eventually(lambda: len(decode(request(session, {"op": "logs"})["data"])) == 256 * 1024)
        self.cli("send", session, "exit")
        eventually(lambda: not (session_dir(session) / "io.sock").exists())
        items = json.loads(self.cli("list", "--json").stdout)
        self.assertEqual(items[0]["status"], "exited")
        self.assertEqual(items[0]["exit_code"], 0)
        self.assertIn("GOODBYE", self.cli("logs", session).stdout)
        self.assertLessEqual((session_dir(session) / "output.tail").stat().st_size, 256 * 1024)

    def test_stop_escalates_and_cleans_socket(self):
        session = self.start()
        self.cli("send", session, "ignore-term")
        eventually(lambda: "IGNORING" in self.cli("logs", session).stdout)
        self.cli("stop", session)
        eventually(lambda: not (session_dir(session) / "io.sock").exists(), timeout=6)
        meta = json.loads((session_dir(session) / "session.json").read_text())
        self.assertEqual(meta["exit_code"], -signal.SIGKILL)

    def test_malformed_request_does_not_kill_session(self):
        session = self.start()
        conn, stream = self.connect(session, read_only=True)
        stream.readline()
        stream.readline()
        conn.sendall(b"not-json\n")
        self.assertIn("error", json.loads(stream.readline()))
        conn.sendall(frame({"op": "info"}))
        self.assertEqual(json.loads(stream.readline())["session"]["status"], "running")
        self.assertEqual((session_dir(session) / "io.sock").stat().st_mode & 0o777, 0o600)
        stream.close()
        conn.close()

    def test_interactive_attach_detach_and_terminal_restore(self):
        session = self.start()
        master, slave = pty.openpty()
        old = termios.tcgetattr(slave)
        client = subprocess.Popen([sys.executable, str(ROOT / "run.py"), "attach", session],
                                  stdin=slave, stdout=slave, stderr=slave)
        received = bytearray()

        def read_until(text):
            def check():
                if select.select([master], [], [], 0.05)[0]:
                    received.extend(os.read(master, 65536))
                return text in received
            try:
                eventually(check)
            except AssertionError:
                self.fail("Missing %r in terminal output: %r" % (text, bytes(received)))

        try:
            read_until(b"READY")
            os.write(master, b"interactive\r")
            read_until(b"ANSWER:interactive")
            os.write(master, b"\x03")
            read_until(b"INTERRUPTED")
            os.write(master, b"\x1d")
            self.assertEqual(client.wait(timeout=4), 0)
            restored = termios.tcgetattr(slave)
            # macOS sets the transient PENDIN bit when returning to canonical
            # mode. All user-controlled modes (including ECHO/ISIG) must match.
            restored[3] &= ~getattr(termios, "PENDIN", 0)
            old[3] &= ~getattr(termios, "PENDIN", 0)
            self.assertEqual(restored, old)
            self.assertEqual(request(session, {"op": "info"})["session"]["status"], "running")
        finally:
            if client.poll() is None:
                client.kill()
                client.wait()
            os.close(master)
            os.close(slave)

    def test_packaged_ssh_transport_with_local_ssh_fixture(self):
        # Runs the actual deployment, shell quoting, zipapp and stdio bridge.
        # SSH authentication/networking is deliberately not claimed by this test.
        home = self.root / "remote-home"
        home.mkdir()
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        ssh = bin_dir / "ssh"
        ssh.write_text("#!/usr/bin/env python3\nimport os, sys\nos.execv('/bin/sh', ['sh', '-c', sys.argv[-1]])\n")
        ssh.chmod(0o700)
        with mock.patch.dict(os.environ, {"HOME": str(home), "PATH": str(bin_dir) + ":" + os.environ["PATH"]}):
            self.cli("install", "fixture-host")
            self.assertTrue((home / ".local/share/macrelay/macrelay.pyz").exists())
            session = self.start(("--host", "fixture-host"))
            text = "literal $(touch %s) ' ; `echo bad`" % (self.root / "INJECTED")
            self.cli("--host", "fixture-host", "send", session, text)
            eventually(lambda: "ANSWER:" + text in self.cli("--host", "fixture-host", "logs", session).stdout)
            self.assertFalse((self.root / "INJECTED").exists())
            self.assertEqual(json.loads(self.cli("--host", "start", "list", "--json").stdout)[0]["id"], session)
            from macrelay.transport import open_bridge
            process = open_bridge(session, "fixture-host")
            try:
                process.stdin.write(frame({"op": "attach", "read_only": True}))
                process.stdin.flush()
                self.assertEqual(json.loads(process.stdout.readline())["event"], "attached")
            finally:
                process.stdin.close()
                process.wait(timeout=4)
                process.stdout.close()

    def test_validation_and_resume_argv(self):
        self.assertNotEqual(self.cli("logs", "../escape", check=False).returncode, 0)
        bad = self.cli("start", "claude", "--cwd", str(self.root / "missing"), check=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual(agent_command("codex", str(self.agent), resume="session-id")[-2:], ["resume", "session-id"])
        self.assertEqual(agent_command("claude", str(self.agent), background="abc")[-2:], ["attach", "abc"])
        with self.assertRaises(ValueError):
            ssh_prefix("-oProxyCommand=bad")
        command = remote_command(["send", "abc", "$(touch /tmp/never)"], "python 3")
        self.assertIn(shlex.quote("$(touch /tmp/never)"), command)


if __name__ == "__main__":
    unittest.main()
