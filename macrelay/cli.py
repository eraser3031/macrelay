import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from . import __version__
from .common import encode, request
from . import host as host_api
from .transport import bridge, build, install, remote_command, ssh_prefix


def parser():
    result = argparse.ArgumentParser(description="Control coding agents on your Mac over SSH.")
    result.add_argument("--version", action="version", version="macrelay " + __version__)
    result.add_argument("--host", help="SSH alias or user@hostname of the execution Mac")
    result.add_argument("--remote-python", default="python3", help="Python executable on the execution Mac")
    sub = result.add_subparsers(dest="command", required=True, metavar="COMMAND")
    setup = sub.add_parser("install", help="Copy this tool to the host over SSH")
    setup.add_argument("destination")
    package = sub.add_parser("build", help="Build a dependency-free .pyz executable")
    package.add_argument("--output", default="dist/macrelay.pyz")
    sub.add_parser("doctor", help="Check host Python, coding CLIs and SSH client")
    start = sub.add_parser("start", help="Start a persistent agent on the host")
    start.add_argument("agent", choices=["codex", "claude"])
    start.add_argument("--cwd", required=True, help="Project directory on the execution Mac")
    start.add_argument("--name")
    start.add_argument("--executable", help="Host agent executable path (optional)")
    resume = start.add_mutually_exclusive_group()
    resume.add_argument("--resume", help="Resume a saved conversation; stop its original writer first")
    resume.add_argument("--background-id", help="Attach an existing Claude background session")
    listing = sub.add_parser("list", help="List sessions managed by macrelay")
    listing.add_argument("--json", action="store_true")
    attached = sub.add_parser("attach", help="Interact with a session; Ctrl-] detaches")
    attached.add_argument("session")
    attached.add_argument("--read-only", action="store_true")
    send = sub.add_parser("send", help="Send text to a detached session's terminal")
    send.add_argument("session")
    send.add_argument("text", help="Literal text; use -- before text starting with a dash")
    send.add_argument("--no-enter", action="store_true")
    log = sub.add_parser("logs", help="Show the most recent 256 KiB of terminal output")
    log.add_argument("session")
    log.add_argument("--raw", action="store_true", help="Write original terminal bytes, including escape codes")
    stop = sub.add_parser("stop", help="Terminate the managed process (TERM, then KILL after 3s)")
    stop.add_argument("session")
    discover = sub.add_parser("discover", help="Inspect existing Claude agents or tmux sessions")
    discover.add_argument("provider", choices=["claude", "tmux"])
    existing = sub.add_parser("attach-existing", help="Use the provider's native attach facility")
    existing.add_argument("provider", choices=["claude", "tmux"])
    existing.add_argument("session")
    for name in ("_serve", "_bridge"):
        internal = sub.add_parser(name)
        internal.add_argument("session")
    return result


def check_tool(name):
    executable = shutil.which(name)
    if not executable:
        return dict(path=None, ok=False, detail="not found")
    try:
        check = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=8)
        return dict(path=executable, ok=check.returncode == 0,
                    detail=(check.stdout + check.stderr).strip()[:1200])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return dict(path=executable, ok=False, detail=str(exc))


def existing_command(provider, session=None):
    if session is not None and (not session or session.startswith("-")):
        raise ValueError("Invalid existing session ID")
    if provider == "claude":
        return ["claude", "attach", session] if session else ["claude", "agents", "--json"]
    return (["tmux", "attach-session", "-t", "=" + session] if session else
            ["tmux", "list-sessions", "-F", "#{session_name}\t#{session_windows}\t#{session_attached}"])


def print_logs(data, raw=False):
    if raw:
        sys.stdout.buffer.write(data)
    else:
        # Escape all terminal control characters in inspection mode. Raw logs and
        # interactive attach are explicitly terminal streams from the trusted host.
        text = data.decode("utf-8", errors="replace")
        sys.stdout.write("".join(c if c in "\n\t" or c.isprintable() else "\\x%02x" % ord(c) for c in text))


def run(argv):
    args = parser().parse_args(argv)
    if args.command == "install":
        install(args.destination, args.remote_python)
        print("Installed on %s. Run: macrelay --host %s doctor" % (args.destination, args.destination))
        return 0
    if args.command == "build":
        build(Path(args.output).resolve())
        print(str(Path(args.output).resolve()))
        return 0
    if args.command == "attach":
        from .terminal import attach
        return attach(args.session, args.host, args.remote_python, args.read_only)
    if args.command == "attach-existing":
        command = existing_command(args.provider, args.session)
        if args.host:
            command = ssh_prefix(args.host, tty=True) + [
                'export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"; exec ' + shlex.join(command)]
        return subprocess.call(command)
    if args.host:
        # Forward only the subcommand arguments. Never parse them through a local
        # shell; remote_command shell-quotes every argument for the remote shell.
        index = 0
        while argv[index].startswith("--"):
            index += 1 if "=" in argv[index] else 2
        return subprocess.call(ssh_prefix(args.host) + [remote_command(argv[index:], args.remote_python)])
    if args.command == "_serve":
        host_api.Broker(args.session).run()
    elif args.command == "_bridge":
        bridge(args.session)
    elif args.command == "doctor":
        tools = {name: check_tool(name) for name in ("codex", "claude")}
        print(json.dumps(dict(python=sys.version.split()[0], executable=sys.executable,
                              agents=tools, ssh=shutil.which("ssh"), tmux=shutil.which("tmux")), indent=2))
        return 0 if any(tool["ok"] for tool in tools.values()) else 1
    elif args.command == "start":
        result = host_api.create(args.agent, args.cwd, args.name, args.executable, args.resume, args.background_id)
        print(json.dumps(result, ensure_ascii=True))
    elif args.command == "list":
        items = host_api.sessions()
        if args.json:
            print(json.dumps(items, ensure_ascii=True))
        elif not items:
            print("No managed sessions. Use start, or discover for existing sessions.")
        else:
            for item in items:
                print("%s  %-11s %-7s %s  %s" %
                      (item["id"], item["status"], item["agent"],
                       json.dumps(item["name"], ensure_ascii=True), json.dumps(item["cwd"], ensure_ascii=True)))
    elif args.command == "send":
        data = args.text.encode() + (b"" if args.no_enter else b"\r")
        request(args.session, {"op": "send", "data": encode(data)})
        print("Input queued (terminal input, not a guarantee that the agent accepted a prompt).")
    elif args.command == "logs":
        print_logs(host_api.logs(args.session), args.raw)
    elif args.command == "stop":
        request(args.session, {"op": "stop"})
        print("Stop requested. Use list to confirm exit.")
    elif args.command == "discover":
        return subprocess.call(existing_command(args.provider))
    return 0


def main():
    try:
        raise SystemExit(run(sys.argv[1:]))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("macrelay: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
