import os
from pathlib import Path
import re
import selectors
import shlex
import socket
import subprocess
import sys
import tempfile
import uuid
import zipapp

from .common import launch_prefix, session_dir, socket_path

REMOTE_ARCHIVE = '"$HOME/.local/share/macrelay/macrelay.pyz"'


def ssh_prefix(host, tty=False):
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@:\-]*", host):
        raise ValueError("Use an SSH config alias or user@hostname for --host")
    return ["ssh", "-tt" if tty else "-T", "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3", "--", host]


def remote_command(args, python="python3"):
    # Common GUI and SSH PATH differences on macOS. Authentication and host-key
    # verification remain entirely with the user's OpenSSH configuration.
    return ('export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"; '
            + shlex.quote(python) + " " + REMOTE_ARCHIVE + " " + shlex.join(args))


def install(host, python="python3"):
    with tempfile.TemporaryDirectory(prefix="macrelay-build-") as temporary:
        artifact = Path(temporary) / "macrelay.pyz"
        current = Path(sys.argv[0]).resolve()
        if current.suffix == ".pyz":
            artifact.write_bytes(current.read_bytes())
        else:
            build(artifact)
        suffix = uuid.uuid4().hex
        target = '"$HOME/.local/share/macrelay/.upload-%s"' % suffix
        command = ('umask 077; mkdir -p "$HOME/.local/share/macrelay" && cat > '
                   + target + " && " + shlex.quote(python) + " " + target
                   + " --version && mv " + target + " " + REMOTE_ARCHIVE)
        with artifact.open("rb") as source:
            subprocess.run(ssh_prefix(host) + [command], stdin=source, check=True)


def build(destination):
    import shutil
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    current = Path(sys.argv[0]).resolve()
    if current.suffix == ".pyz":
        if current != destination:
            shutil.copy2(current, destination)
        return
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="macrelay-package-") as temporary:
        staging = Path(temporary)
        shutil.copytree(root / "macrelay", staging / "macrelay",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        if (root / "LICENSE").is_file():
            shutil.copy2(root / "LICENSE", staging / "LICENSE")
        zipapp.create_archive(staging, destination, main="macrelay.cli:main",
                              interpreter="/usr/bin/env python3", compressed=True)


def open_bridge(session, host=None, python="python3"):
    command = (ssh_prefix(host) + [remote_command(["_bridge", session], python)]
               if host else launch_prefix() + ["_bridge", session])
    return subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)


def bridge(session):
    # This short-lived SSH-side process does not own the agent. EOF only detaches.
    with socket.socket(socket.AF_UNIX) as conn:
        conn.connect(socket_path(session_dir(session)))
        with selectors.DefaultSelector() as selector:
            selector.register(conn, selectors.EVENT_READ)
            selector.register(sys.stdin.buffer, selectors.EVENT_READ)
            while True:
                for key, _ in selector.select():
                    if key.fileobj is conn:
                        data = conn.recv(65536)
                        if not data:
                            return
                        sys.stdout.buffer.write(data)
                        sys.stdout.buffer.flush()
                    else:
                        data = os.read(sys.stdin.fileno(), 65536)
                        if not data:
                            return
                        conn.sendall(data)
