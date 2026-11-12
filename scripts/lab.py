"""Shared paths, SQLite telemetry, and process identity checks for the local lab."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("ONCALL_DATA", ROOT / "data")).resolve()
SANDBOX = Path(os.environ.get("ONCALL_SANDBOX", ROOT / "sandbox" / "checkout-service")).resolve()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@contextmanager
def metrics():
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA / "metrics.db", timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("CREATE TABLE IF NOT EXISTS requests (ts TEXT, route TEXT, status INTEGER, latency_ms REAL)")
        conn.execute("CREATE TABLE IF NOT EXISTS samples (ts TEXT, pid INTEGER, rss_mb REAL, version TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS events (ts TEXT, kind TEXT, detail TEXT)")
        yield conn
        conn.commit()
    finally:
        conn.close()


def event(kind, **detail):
    with metrics() as conn:
        conn.execute("INSERT INTO events VALUES (?, ?, ?)", (now(), kind, json.dumps(detail)))


def write_state(name, process):
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / f"{name}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"pid": process.pid, "created": process.create_time()}))
    tmp.replace(path)


def managed(name):
    """PID reuse must never let devctl kill an unrelated process."""
    try:
        state = json.loads((DATA / f"{name}.json").read_text())
        proc = psutil.Process(state["pid"])
        if abs(proc.create_time() - state["created"]) < 0.01 and proc.status() != psutil.STATUS_ZOMBIE:
            return proc
    except (OSError, ValueError, KeyError, psutil.Error):
        pass
    return None


def stop(name):
    proc = managed(name)
    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except psutil.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    (DATA / f"{name}.json").unlink(missing_ok=True)


def request_summary(since):
    with metrics() as conn:
        total, errors, network = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(status>=500),0), COALESCE(SUM(status=0),0) FROM requests WHERE ts>=?",
            (since,),
        ).fetchone()
    return {"requests": total, "http_5xx": errors, "network_errors": network,
            "http_5xx_rate": errors / total if total else None}
