import json
import os
import selectors
import shutil
import signal
import subprocess
import sys
import termios
import tty

from .common import MAX_FRAME, decode, encode, frame
from .transport import open_bridge


def attach(session, host=None, python="python3", read_only=False):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("attach requires an interactive terminal; use send and logs for scripts")
    process = open_bridge(session, host, python)
    old = termios.tcgetattr(sys.stdin)
    old_winch = signal.getsignal(signal.SIGWINCH)
    old_signals = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}
    incoming = bytearray()
    attached = False
    needs_resize = True

    def send(value):
        packet = frame(value)
        # Popen's unbuffered pipe writes can be short.
        while packet:
            count = os.write(process.stdin.fileno(), packet)
            packet = packet[count:]

    def window_changed(*_):
        nonlocal needs_resize
        needs_resize = True

    def terminate(signum, _):
        raise SystemExit(128 + signum)

    def dimensions():
        size = shutil.get_terminal_size((80, 24))
        return dict(rows=max(1, min(size.lines or 24, 1000)),
                    cols=max(1, min(size.columns or 80, 1000)))

    try:
        send(dict(op="attach", read_only=read_only, **dimensions()))
        signal.signal(signal.SIGWINCH, window_changed)
        for sig in old_signals:
            signal.signal(sig, terminate)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "host")
            selector.register(sys.stdin, selectors.EVENT_READ, "input")
            while True:
                if attached and needs_resize and not read_only:
                    send(dict(op="resize", **dimensions()))
                    needs_resize = False
                for key, _ in selector.select(0.1):
                    if key.data == "input":
                        data = os.read(sys.stdin.fileno(), 65536)
                        if not data or b"\x1d" in data:  # Ctrl-]
                            return 0
                        if attached and not read_only:
                            send({"op": "input", "data": encode(data)})
                    else:
                        data = os.read(process.stdout.fileno(), 65536)
                        if not data:
                            raise ValueError("Connection closed. The host session may still be running; use list/attach to reconnect.")
                        incoming.extend(data)
                        if len(incoming) > MAX_FRAME:
                            raise ValueError("Host frame exceeds protocol limit")
                        while b"\n" in incoming:
                            line, _, rest = incoming.partition(b"\n")
                            incoming = bytearray(rest)
                            message = json.loads(line)
                            if message.get("error"):
                                raise ValueError(message["error"])
                            if message.get("event") == "attached":
                                print("Connected. Ctrl-] detaches; Ctrl-C goes to the agent.", file=sys.stderr)
                                tty.setraw(sys.stdin.fileno())
                                attached = True
                            elif message.get("event") == "output":
                                sys.stdout.buffer.write(decode(message["data"]))
                                sys.stdout.buffer.flush()
                            elif message.get("event") == "exit":
                                code = message["code"]
                                return code if code >= 0 else 128 - code
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        signal.signal(signal.SIGWINCH, old_winch)
        for sig, handler in old_signals.items():
            signal.signal(sig, handler)
        # Clear modes commonly set by agent TUIs before restoring the user's shell.
        if attached:
            sys.stdout.write("\x1b[?1049l\x1b[?2004l\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?25h\x1b[0m\r\n")
            sys.stdout.flush()
        process.stdin.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
