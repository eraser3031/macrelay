import base64
import json
import os
from pathlib import Path
import re
import socket
import sys

MAX_FRAME = 1024 * 1024
REPLAY_BYTES = 256 * 1024


def state_root():
    path = Path(os.environ.get("MACRELAY_HOME", "~/.macrelay")).expanduser().resolve()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError("MACRELAY_HOME must be owned by you with permissions 0700")
    return path


def session_dir(session):
    if not re.fullmatch(r"[0-9a-f]{12}", session):
        raise ValueError("Invalid session ID (expected 12 hexadecimal characters)")
    return state_root() / session


def socket_path(directory):
    path = str(directory / "io.sock")
    if len(os.fsencode(path)) > 100:
        raise ValueError("MACRELAY_HOME is too long for a Unix socket; use a shorter path")
    return path


def write_json(path, data):
    temp = path.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as file:
        os.chmod(temp, 0o600)
        json.dump(data, file, ensure_ascii=False)
    os.replace(temp, path)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def frame(value):
    return (json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n").encode()


def encode(data):
    return base64.b64encode(data).decode("ascii")


def decode(data):
    return base64.b64decode(data, validate=True)


def launch_prefix():
    # A zipapp is self-contained. Source mode uses an absolute entry script so a
    # detached session does not depend on the caller's current directory.
    archive = Path(sys.argv[0]).resolve()
    if archive.suffix == ".pyz":
        return [sys.executable, str(archive)]
    source_entry = Path(__file__).resolve().parent.parent / "run.py"
    if source_entry.is_file():
        return [sys.executable, str(source_entry)]
    return [sys.executable, "-m", "macrelay"]


def request(session, payload, timeout=5):
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(timeout)
        conn.connect(socket_path(session_dir(session)))
        conn.sendall(frame(payload))
        with conn.makefile("rb") as stream:
            line = stream.readline(MAX_FRAME + 1)
    if not line or len(line) > MAX_FRAME:
        raise ValueError("Host returned an invalid response")
    result = json.loads(line)
    if result.get("error"):
        raise ValueError(result["error"])
    return result
