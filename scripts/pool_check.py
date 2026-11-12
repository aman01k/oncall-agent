"""Check that database connection-pool exhaustion really happens.

Starts the real checkout-api server twice and sends 20 concurrent requests
to /orders/history each time:

  healthy    pool 5 + overflow 5, no slow query      -> expect no 5xx
  exhausted  pool 2 + overflow 0, 3 s slow query,    -> expect 5xx with
             2 s pool timeout                           sqlalchemy TimeoutError

Each config uses its own database and log under data/pool_check/<name>/.

Usage:
    .venv/bin/python scripts/pool_check.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.getenv("POOL_CHECK_PORT", "8001"))
BASE = f"http://127.0.0.1:{PORT}"
CONCURRENCY = 20

CONFIGS = {
    "healthy": {"POOL_SIZE": "5", "MAX_OVERFLOW": "5", "POOL_TIMEOUT": "2", "HISTORY_QUERY_DELAY": "0"},
    "exhausted": {"POOL_SIZE": "2", "MAX_OVERFLOW": "0", "POOL_TIMEOUT": "2", "HISTORY_QUERY_DELAY": "3"},
}


def wait_for_health(timeout_s: float = 15) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE}/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("service did not become healthy")


def one_request(i: int) -> int | str:
    try:
        r = httpx.get(f"{BASE}/orders/history", params={"customer_id": f"c-{i % 3}"}, timeout=15)
        return r.status_code
    except httpx.HTTPError as e:
        return f"client:{type(e).__name__}"


def run_config(name: str, overrides: dict) -> dict:
    workdir = ROOT / "data" / "pool_check" / name
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True)
    log_file = workdir / "service.jsonl"
    env = {**os.environ, **overrides, "APP_DB": str(workdir / "app.db"), "LOG_FILE": str(log_file)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "service.app:app", "--port", str(PORT), "--no-access-log",
         "--log-level", "warning"],
        cwd=ROOT, env=env,
    )
    try:
        wait_for_health()
        httpx.post(f"{BASE}/checkout", json={"customer_id": "c-0", "items": [{"sku": "SKU-1001", "qty": 1}]},
                   timeout=10).raise_for_status()
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            results = list(pool.map(one_request, range(CONCURRENCY)))
        elapsed = round(time.perf_counter() - start, 1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    lines = [json.loads(x) for x in log_file.read_text().splitlines() if x.strip()]
    errors = [x for x in lines if x.get("event") == "request" and x.get("status", 0) >= 500]
    return {
        "config": name,
        "settings": overrides,
        "elapsed_s": elapsed,
        "status_counts": dict(Counter(results)),
        "logged_5xx": len(errors),
        "exc_types": dict(Counter(x.get("exc_type") for x in errors)),
        "sample_error": errors[0] if errors else None,
    }


def main() -> int:
    ok = True
    for name, overrides in CONFIGS.items():
        r = run_config(name, overrides)
        print(f"[{name}] {r['settings']}")
        print(f"  {CONCURRENCY} concurrent requests in {r['elapsed_s']}s -> {r['status_counts']}")
        print(f"  logged 5xx: {r['logged_5xx']}  exception types: {r['exc_types']}")
        if r["sample_error"]:
            print(f"  sample log line: {json.dumps(r['sample_error'])[:400]}")
        if name == "healthy" and r["logged_5xx"]:
            ok = False
            print("  FAIL: healthy config produced 5xx")
        if name == "exhausted" and r["exc_types"].get("TimeoutError", 0) == 0:
            ok = False
            print("  FAIL: exhausted config did not produce a pool TimeoutError")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
