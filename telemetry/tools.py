"""Read-only, bounded investigation tools against a frozen evidence folder."""
from __future__ import annotations
import json
import re
import shlex
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Tools:
    def __init__(self, source, runbooks=None):
        self.source = Path(source).resolve()
        self.runbooks = Path(runbooks or ROOT / "runbooks").resolve()
        self.alert = json.loads((self.source / "alert.json").read_text())
        self.clock = timestamp(self.alert["fired_at"])

    def read(self, name):
        return json.loads((self.source / name).read_text())

    def recent(self, rows, minutes):
        if not 1 <= minutes <= 120:
            raise ValueError("minutes must be between 1 and 120")
        start = self.clock - timedelta(minutes=minutes)
        return [r for r in rows if start <= timestamp(r["ts"]) <= self.clock]

    def search_logs(self, query="", minutes=10):
        rows = self.recent(self.read("logs.json"), minutes)
        def matches(row):
            for term in shlex.split(query):
                if ":" in term:
                    key, value = term.split(":", 1)
                    if key not in {"service", "level", "status", "route"}:
                        raise ValueError("Supported filters: service:, level:, status:5xx, route:. Or use literal text.")
                    if key == "status" and value.lower() == "5xx":
                        if not 500 <= row.get("status", 0) < 600:
                            return False
                    elif str(row.get(key, "")).casefold() != value.casefold():
                        return False
                elif term.casefold() not in json.dumps(row).casefold():
                    return False
            return True
        rows = [r for r in rows if (r.get("status", 0) >= 500 or r.get("level") == "ERROR")
                and matches(r)]
        groups = {}
        for row in rows:
            signature = f"{row.get('exc_type', 'HTTPError')} {row.get('route')} {row.get('status')}"
            group = groups.setdefault(signature, {"signature": signature, "count": 0,
                "first_seen": row["ts"], "last_seen": row["ts"], "samples": []})
            group["count"] += 1
            group["last_seen"] = row["ts"]
            if len(group["samples"]) < 2:
                group["samples"].append({k: v for k, v in row.items() if k in
                    {"id", "ts", "route", "status", "exc_type", "exc", "msg", "version"}})
        return {"matching_errors": len(rows), "groups": sorted(groups.values(), key=lambda g: -g["count"])[:4]}

    def query_metrics(self, minutes=10):
        requests = self.recent(self.read("requests.json"), minutes)
        samples = self.recent(self.read("samples.json"), minutes)
        events = self.recent(self.read("events.json"), minutes)
        bins = {}
        for row in requests:
            slot = row["ts"][:18] + "0Z"  # ten-second buckets
            bucket = bins.setdefault(slot, Counter())
            bucket["requests"] += 1
            bucket["http_5xx"] += int(row["status"] >= 500)
            bucket["network_errors"] += int(row["status"] == 0)
        latencies = sorted(r["latency_ms"] for r in requests)
        rss = [r["rss_mb"] for r in samples]
        latest = samples[-1]["ts"] if samples else None
        errors = sum(r["status"] >= 500 for r in requests)
        summary = f"Observed {errors} HTTP 5xx responses among {len(requests)} requests."
        if rss:
            summary += f" RSS ranged from {min(rss):.1f} to {max(rss):.1f} MiB."
        return {"summary": summary, "requests": len(requests), "http_5xx": errors,
                "p95_latency_ms": latencies[min(len(latencies)-1, int(len(latencies)*.95))] if latencies else None,
                "rss_min_mb": round(min(rss), 1) if rss else None,
                "rss_max_mb": round(max(rss), 1) if rss else None,
                "last_sample": latest, "stale": not latest or (self.clock-timestamp(latest)).total_seconds() > 5,
                "buckets": [{"ts": t, **dict(b)} for t, b in sorted(bins.items())[-12:]],
                "events": [e for e in events if e["kind"] in {"memory_limit_exceeded", "worker_exit"}][-4:]}

    def list_deploys(self, minutes=10):
        return {"deploys": list(reversed(self.recent(self.read("deploys.json"), minutes)[-10:]))}

    def git_show(self, revision):
        commits = self.read("commits.json")
        if revision not in commits:
            raise ValueError("Unknown revision; use a full SHA or tag returned by list_deploys")
        return commits[revision]

    def health_check(self):
        return self.read("health.json")

    def search_runbooks(self, query):
        words = set(re.findall(r"[a-z0-9_]+", query.lower()))
        matches = []
        for path in sorted(self.runbooks.glob("*.md")):
            content = path.read_text()
            score = sum(min(5, content.lower().count(word)) for word in words)
            if score:
                matches.append({"id": path.stem, "title": content.splitlines()[0].lstrip("# "), "score": score})
        return {"matches": sorted(matches, key=lambda m: -m["score"])[:5]}

    def read_runbook(self, id):
        if not re.fullmatch(r"[a-z0-9_-]+", id):
            raise ValueError("Invalid runbook ID")
        path = self.runbooks / f"{id}.md"
        if not path.is_file():
            raise ValueError("Runbook not found")
        return {"id": id, "content": path.read_text()[:3200]}

    def call(self, name, arguments):
        if name not in TOOL_NAMES:
            raise ValueError("Unknown read-only tool")
        value = getattr(self, name)(**arguments)
        encoded = json.dumps(value, ensure_ascii=False)
        if len(encoded) > 4000:
            return {"content": encoded[:3600], "truncated": True, "total_characters": len(encoded)}
        return value


TOOL_NAMES = {"search_logs", "query_metrics", "list_deploys", "git_show", "health_check",
              "search_runbooks", "read_runbook"}


def schema(name, description, properties=None, required=None):
    return {"type": "function", "function": {"name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": required or [],
                       "additionalProperties": False}}}


WINDOW = {"minutes": {"type": "integer", "minimum": 1, "maximum": 120}}
SCHEMAS = [
    schema("search_logs", "Search errors before alert time. Empty query returns all. Supports literal words and service:, level:, status:5xx, route: filters.",
           {"query": {"type": "string"}, **WINDOW}),
    schema("query_metrics", "Request errors, latency, RSS, restarts and data freshness.", WINDOW),
    schema("list_deploys", "Recent real deployments, NEWEST FIRST, with full SHAs and tags. Latest can be unrelated.", WINDOW),
    schema("git_show", "Inspect one revision's code diff to identify the causal commit.",
           {"revision": {"type": "string"}}, ["revision"]),
    schema("health_check", "Health results captured at alert time."),
    schema("search_runbooks", "Keyword search over known incident guides.", {"query": {"type": "string"}}, ["query"]),
    schema("read_runbook", "Read a guide by the ID returned from search.", {"id": {"type": "string"}}, ["id"]),
]
