"""Local lab control: up/down/inject/reset/restart/rollback/check."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import socket
import subprocess
import sys
import time

import httpx
import psutil

from bootstrap_sandbox import FAULT_TAGS, HEALTHY, bootstrap, git
from lab import DATA, ROOT, event, managed, now, request_summary, stop, write_state


def down():
    stop("loadgen")
    stop("supervisor")
    # Also clean up a worker left after an abnormal supervisor exit.
    stop("worker")


def up(port=8001, cap_mb=192):
    if managed("supervisor"):
        raise RuntimeError("Lab already running; use down first")
    bootstrap()
    # Never interpret an unrelated listener as our healthy service.
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
    DATA.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    with (DATA / "supervisor.log").open("a") as output:
        proc = subprocess.Popen([sys.executable, str(ROOT / "scripts/supervisor.py"), "--port", str(port),
                                 "--cap-mb", str(cap_mb)], stdout=output, stderr=output,
                                env=env, start_new_session=True)
    write_state("supervisor", psutil.Process(proc.pid))
    try:
        with httpx.Client(trust_env=False, timeout=0.5) as client:
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError(f"Supervisor exited; see {DATA / 'supervisor.log'}")
                try:
                    if client.get(f"http://127.0.0.1:{port}/health").status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError(f"Service did not start; see {DATA / 'worker.log'}")
        version = git("describe", "--tags", "--exact-match")
        path = DATA / "deploys.json"
        deploys = json.loads(path.read_text()) if path.exists() else []
        deploys.append({"id": f"D{len(deploys) + 1}", "ts": now(), "version": version,
                        "sha": git("rev-parse", version), "summary": git("log", "-1", "--format=%s", version)})
        path.write_text(json.dumps(deploys, indent=2) + "\n")
        event("deploy", version=version, sha=git("rev-parse", "HEAD"))
        with (DATA / "loadgen.log").open("a") as output:
            load = subprocess.Popen([sys.executable, str(ROOT / "scripts/loadgen.py"),
                                     "--url", f"http://127.0.0.1:{port}"],
                                    stdout=output, stderr=output, env=env, start_new_session=True)
        write_state("loadgen", psutil.Process(load.pid))
        (DATA / "lab-settings.json").write_text(json.dumps({"port": port, "cap_mb": cap_mb}))
        return {"version": version, "url": f"http://127.0.0.1:{port}", "data": str(DATA)}
    except BaseException:
        down()
        raise


def settings():
    path = DATA / "lab-settings.json"
    return json.loads(path.read_text()) if path.exists() else {"port": 8001, "cap_mb": 192}


def deploy(tag):
    bootstrap()
    # Resolve only an exact known tag, never arbitrary refs or shell fragments.
    allowed = {HEALTHY, *FAULT_TAGS.values(), "v1.1.0", "v1.2.0", "v1.3.0"}
    if tag not in allowed:
        raise ValueError(f"Unsupported release: {tag}")
    opts = settings()
    down()
    git("checkout", "-q", "--detach", tag)
    return up(**opts)


def check(seconds):
    since = now()
    time.sleep(seconds)
    result = request_summary(since)
    result.update(supervisor_running=bool(managed("supervisor")), loadgen_running=bool(managed("loadgen")))
    return result


def inject(scenario):
    tag = FAULT_TAGS[scenario]
    deploy(tag.removesuffix(".1") + ".0")
    # Both versions actually run; deploy history is measured, not invented.
    time.sleep(2)
    return deploy(tag)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("up")
    start.add_argument("--port", type=int, default=8001)
    start.add_argument("--cap-mb", type=float, default=192)
    sub.add_parser("down")
    sub.add_parser("reset")
    sub.add_parser("restart")
    inject_parser = sub.add_parser("inject")
    inject_parser.add_argument("scenario", choices=FAULT_TAGS)
    rollback = sub.add_parser("rollback")
    rollback.add_argument("tag")
    capture_parser = sub.add_parser("capture")
    capture_parser.add_argument("destination")
    status = sub.add_parser("check")
    status.add_argument("--seconds", type=float, default=10)
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    try:
        with (DATA / "control.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.command == "up":
                result = up(args.port, args.cap_mb)
            elif args.command == "down":
                down()
                result = {"status": "stopped"}
            elif args.command == "inject":
                result = inject(args.scenario)
            elif args.command == "reset":
                result = deploy(HEALTHY)
            elif args.command == "rollback":
                result = deploy(args.tag)
            elif args.command == "restart":
                opts = settings()
                down()
                result = up(**opts)
            elif args.command == "capture":
                from capture import capture
                result = {"snapshot": str(capture(args.destination))}
            else:
                if not 0 < args.seconds <= 120:
                    raise ValueError("check window must be between 0 and 120 seconds")
                result = check(args.seconds)
        print(json.dumps(result, indent=2))
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError, psutil.Error) as exc:
        parser.exit(1, f"devctl: {exc}\n")


if __name__ == "__main__":
    main()
