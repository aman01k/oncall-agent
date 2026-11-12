"""Build isolated, tagged service versions without touching the project history."""
from __future__ import annotations

import json
import shutil
import subprocess

from lab import ROOT, SANDBOX

FAULT_TAGS = {"bad_deploy": "v1.1.1", "pool_exhaustion": "v1.2.1", "memory_leak": "v1.3.1"}
HEALTHY = "v1.0.0"


def git(*args):
    return subprocess.check_output(["git", "-C", str(SANDBOX), *args], text=True).strip()


def commit(message, tag):
    git("add", "service", "release.json")
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", message)
    git("tag", tag)


def bootstrap():
    if (SANDBOX / ".git").exists():
        for tag in [HEALTHY, *FAULT_TAGS.values()]:
            git("rev-parse", "--verify", f"refs/tags/{tag}")
        return
    if SANDBOX.exists() and any(SANDBOX.iterdir()):
        raise RuntimeError(f"Refusing to overwrite non-empty folder: {SANDBOX}")
    SANDBOX.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "service", SANDBOX / "service", ignore=shutil.ignore_patterns("__pycache__"))
    git("init", "-q", "-b", "main")
    # Inherit the user's real identity; fail if it is missing rather than inventing one.
    for key in ("user.name", "user.email"):
        value = subprocess.check_output(["git", "-C", str(ROOT), "config", key], text=True).strip()
        git("config", key, value)
    (SANDBOX / "release.json").write_text(json.dumps({"description": "Checkout service"}) + "\n")
    commit("Initial checkout implementation", HEALTHY)
    for scenario, tag in FAULT_TAGS.items():
        git("checkout", "-q", "--detach", HEALTHY)
        if scenario == "bad_deploy":
            (SANDBOX / "service" / "pricing.py").write_text('''"""Currency-aware pricing."""
import zlib

def price_total(prices, items, customer_id):
    context = {"customer_id": customer_id}
    if zlib.crc32(customer_id.encode()) % 10 < 3:
        currency = context["currency"]
    return round(sum(prices[i.sku] * i.qty for i in items), 2)
''')
            message = "Add currency context to pricing"
        elif scenario == "pool_exhaustion":
            path = SANDBOX / "service" / "config.py"
            source = path.read_text().replace('_int("POOL_SIZE", 5)', '_int("POOL_SIZE", 2)')
            source = source.replace('_int("MAX_OVERFLOW", 5)', '_int("MAX_OVERFLOW", 0)')
            source = source.replace('_float("HISTORY_QUERY_DELAY", 0.0)', '_float("HISTORY_QUERY_DELAY", 3.0)')
            path.write_text(source)
            message = "Reduce database connections and retain history query context"
        else:
            (SANDBOX / "service" / "cache.py").write_text('''"""Keep checkout context available for later requests."""
import os
import threading
from fastapi import HTTPException

_cache = []
_lock = threading.Lock()

def record_checkout(customer_id):
    with _lock:
        _cache.append(os.urandom(2 * 1024 * 1024))
        if len(_cache) >= 48:
            raise HTTPException(status_code=503, detail="checkout temporarily unavailable")
''')
            message = "Cache checkout context for request reuse"
        commit(message, tag.removesuffix(".1") + ".0")
        # Later metadata-only deploy is a decoy; rolling it back leaves the bug.
        (SANDBOX / "release.json").write_text(json.dumps({"description": "Checkout API documentation update"}) + "\n")
        commit("Update release description", tag)
    git("checkout", "-q", "--detach", HEALTHY)


if __name__ == "__main__":
    bootstrap()
    print(f"Sandbox ready: {SANDBOX}")
