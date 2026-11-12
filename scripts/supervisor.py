"""Run one checkout worker, sample RSS, and enforce a bounded memory limit."""
from __future__ import annotations

import argparse
import fcntl
import os
import signal
import subprocess
import sys
import time

import psutil

from bootstrap_sandbox import git
from lab import DATA, SANDBOX, event, metrics, now, write_state


def run(port, cap_mb):
    DATA.mkdir(parents=True, exist_ok=True)
    # Held for process lifetime: only one supervisor may own this data directory.
    with (DATA / "supervisor.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        write_state("supervisor", psutil.Process())
        stopping = False

        def stop_signal(*_):
            nonlocal stopping
            stopping = True

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, stop_signal)
        child = None
        version = git("describe", "--tags", "--exact-match")
        try:
            with (DATA / "worker.log").open("a") as output:
                while not stopping:
                    if child is None:
                        # No provider keys or inherited fault overrides reach the service.
                        env = {key: value for key, value in os.environ.items()
                               if key in {"PATH", "HOME", "TMPDIR", "LANG", "SYSTEMROOT"}}
                        env.update(APP_DB=str(DATA / "app.db"), LOG_FILE=str(DATA / "logs" / "service.jsonl"),
                                   SERVICE_VERSION=version, PYTHONDONTWRITEBYTECODE="1")
                        child = subprocess.Popen([sys.executable, "-m", "uvicorn", "service.app:app",
                                                  "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
                                                 cwd=SANDBOX, env=env, stdout=output, stderr=output)
                        write_state("worker", psutil.Process(child.pid))
                        event("worker_start", pid=child.pid, version=version)
                    if child.poll() is not None:
                        event("worker_exit", pid=child.pid, returncode=child.returncode, version=version)
                        child = None
                        time.sleep(0.5)
                        continue
                    try:
                        rss = psutil.Process(child.pid).memory_info().rss / 1024**2
                    except psutil.NoSuchProcess:
                        continue
                    with metrics() as conn:
                        conn.execute("INSERT INTO samples VALUES (?, ?, ?, ?)", (now(), child.pid, rss, version))
                    if rss > cap_mb:
                        event("memory_limit_exceeded", pid=child.pid, rss_mb=round(rss, 2), cap_mb=cap_mb,
                              version=version, source="local_supervisor")
                        child.kill()
                        child.wait(timeout=5)
                    time.sleep(0.2)
        finally:
            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            for name in ("worker", "supervisor"):
                (DATA / f"{name}.json").unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--cap-mb", type=float, default=192)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.cap_mb < 128:
        parser.error("valid port and cap >= 128 MiB required")
    run(args.port, args.cap_mb)
