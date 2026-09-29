"""Launch a real CLI without sending prompts, capture startup, then stop it.

Usage: python3 scripts/smoke_live.py claude
This does not test authentication, model responses or approval execution.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macrelay import host
from macrelay.common import request, session_dir


def main():
    agent = sys.argv[1] if len(sys.argv) > 1 else "claude"
    if agent not in ("claude", "codex"):
        raise ValueError("Expected claude or codex")
    with tempfile.TemporaryDirectory(prefix="mr-live-", dir="/tmp") as temporary:
        os.environ["MACRELAY_HOME"] = temporary + "/state"
        project = Path(temporary) / "project"
        project.mkdir()
        session = host.create(agent, str(project))["id"]
        try:
            deadline = time.monotonic() + 10
            data = b""
            while time.monotonic() < deadline:
                data = host.logs(session)
                if data:
                    break
                time.sleep(0.1)
            info = request(session, {"op": "info"})["session"]
            if not data or info["status"] != "running":
                raise RuntimeError("Agent did not produce startup output while running")
            print(json.dumps(dict(agent=agent, status=info["status"],
                                  startup_bytes=len(data), prompt_sent=False)))
        finally:
            try:
                request(session, {"op": "stop"})
            except OSError:
                pass
            deadline = time.monotonic() + 6
            while (session_dir(session) / "io.sock").exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            if (session_dir(session) / "io.sock").exists():
                raise RuntimeError("Session cleanup timed out")


if __name__ == "__main__":
    main()
