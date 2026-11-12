"""Capture real service evidence; answer keys stay outside the evidence folder."""
from __future__ import annotations
import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from bootstrap_sandbox import git
from lab import DATA, ROOT, now


def capture(destination, threshold=True):
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Snapshot folder already exists; choose a new name")
    clock = now()
    start = (datetime.fromisoformat(clock.replace("Z", "+00:00")) - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    db = sqlite3.connect(f"file:{DATA / 'metrics.db'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        evidence = {table: [dict(row) for row in db.execute(f"SELECT * FROM {table} WHERE ts>=? AND ts<=? ORDER BY ts", (start, clock))]
                    for table in ("requests", "samples", "events")}
    finally:
        db.close()
    cutoff = (datetime.fromisoformat(clock.replace("Z", "+00:00"))-timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    recent = [r for r in evidence["requests"] if r["ts"] >= cutoff]
    rate = sum(r["status"] >= 500 for r in recent) / len(recent) if recent else 0
    if threshold and (len(recent) < 20 or rate <= .05):
        raise ValueError(f"Alert threshold not met: {len(recent)} requests, HTTP 5xx rate {rate:.1%}")
    evidence["alert"] = {"service": "checkout-api", "fired_at": clock,
                         "message": "checkout-api HTTP 5xx rate above 5% over 2 minutes",
                         "observed_rate": round(rate, 4), "window_seconds": 120}
    evidence["logs"] = []
    for line in (DATA / "logs/service.jsonl").read_text().splitlines():
        try:
            row = json.loads(line)
            if start <= row["ts"] <= clock:
                evidence["logs"].append(row)
        except (ValueError, KeyError):
            continue  # A concurrent writer can leave one partial line at the end.
    evidence["deploys"] = [d for d in json.loads((DATA / "deploys.json").read_text()) if d["ts"] <= clock]
    evidence["deployment-state"] = evidence["deploys"][-1]
    evidence["commits"] = {}
    for tag in git("tag", "--list").splitlines():
        sha = git("rev-parse", tag)
        item = {"sha": sha, "tag": tag, "summary": git("log", "-1", "--format=%s", tag),
                "diff": git("show", "--format=short", "--no-ext-diff", tag, "--", "service", "release.json")[:10000]}
        evidence["commits"][tag] = evidence["commits"][sha] = item
    settings = json.loads((DATA / "lab-settings.json").read_text())
    health = {}
    with httpx.Client(timeout=3, trust_env=False) as client:
        for path in ("/health", "/health/db"):
            try:
                response = client.get(f"http://127.0.0.1:{settings['port']}{path}")
                health[path] = {"status": response.status_code, "body": response.json()}
            except (httpx.RequestError, ValueError):
                health[path] = {"status": 0, "body": "unreachable"}
    evidence["health"] = {"captured_at": clock, "checks": health}
    destination.mkdir(parents=True)
    for name, value in evidence.items():
        (destination / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--allow-healthy", action="store_true")
    args = parser.parse_args()
    print(capture(args.destination, threshold=not args.allow_healthy))
