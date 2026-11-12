"""Check free-tier LLM providers before building the agent on them.

For each provider with a key in .env, this script:
  1. lists the models the key can use,
  2. runs a short tool-calling conversation (a fake incident with fake tools),
  3. records tokens, latency, rate-limit headers and any errors.

Results are printed and saved to data/provider_check/<provider>-<time>.json
(data/ is git-ignored, so keys and raw responses never reach the repo).

Usage:
    .venv/bin/python scripts/provider_check.py            # all providers with a key
    .venv/bin/python scripts/provider_check.py groq       # one provider
    .venv/bin/python scripts/provider_check.py groq --runs 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, APIStatusError

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "provider_check"

PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "model_env": "GROQ_MODEL",
        # Tried in order if GROQ_MODEL is not set. Model IDs change; the list
        # of models the key can use is printed so you can pick another one.
        "prefer": ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "qwen/qwen3-32b"],
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GEMINI_API_KEY",
        "model_env": "GEMINI_MODEL",
        "prefer": ["gemini-2.5-flash", "gemini-2.0-flash"],
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "key_env": "OLLAMA_API_KEY",  # any non-empty value, e.g. "ollama"
        "model_env": "OLLAMA_MODEL",
        "prefer": ["qwen2.5:7b-instruct", "qwen3:8b"],
    },
}

# --- A tiny fake incident --------------------------------------------------
# The model must call at least two tools and then submit a report. This mirrors
# the shape of the real agent loop without needing the real service.

SYSTEM = (
    "You are an on-call investigation agent. Use the tools to gather evidence "
    "before concluding. Call one tool at a time. When you know the cause, call "
    "submit_report. Do not guess without evidence."
)
ALERT = "ALERT fired_at=2026-11-12T10:05:00Z: checkout-api 5xx rate above 5% over 2m."

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_logs",
            "description": "Search service logs. Returns matching lines grouped by error type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to search for, e.g. 'ERROR'"},
                    "minutes": {"type": "integer", "description": "How far back from the alert to search"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_deploys",
            "description": "List deploys in the last N minutes before the alert.",
            "parameters": {
                "type": "object",
                "properties": {"minutes": {"type": "integer"}},
                "required": ["minutes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_report",
            "description": "Finish the investigation with a root cause.",
            "parameters": {
                "type": "object",
                "properties": {
                    "failure_type": {
                        "type": "string",
                        "enum": ["bad_deploy", "db_pool_exhaustion", "memory_leak", "unknown"],
                    },
                    "culprit": {"type": "string", "description": "e.g. a deploy tag or commit"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["failure_type", "culprit", "evidence"],
            },
        },
    },
]


def fake_tool(name: str, args: dict) -> str:
    if name == "search_logs":
        return json.dumps({
            "groups": [
                {"signature": "KeyError: 'currency' in checkout.price_total", "count": 412,
                 "first_seen": "2026-11-12T10:01:12Z",
                 "sample": "id=L1832 ts=2026-11-12T10:01:12Z route=/checkout status=500 exc=KeyError"},
                {"signature": "WARN slow request /orders/history", "count": 7},
            ]
        })
    if name == "list_deploys":
        return json.dumps({"deploys": [
            {"tag": "v1.3.0", "sha": "a1b2c3d", "at": "2026-11-12T10:00:40Z", "note": "checkout pricing refactor"},
            {"tag": "v1.2.9", "sha": "9f8e7d6", "at": "2026-11-12T09:20:00Z", "note": "update footer text"},
        ]})
    return json.dumps({"error": f"unknown tool {name}"})


# --- Runner ----------------------------------------------------------------

def pick_model(client: OpenAI, cfg: dict) -> tuple[str | None, list[str]]:
    try:
        ids = sorted(m.id.removeprefix("models/") for m in client.models.list())
    except Exception as e:  # noqa: BLE001 - report any listing failure
        print(f"  could not list models: {e}")
        ids = []
    chosen = os.getenv(cfg["model_env"])
    if not chosen:
        chosen = next((m for m in cfg["prefer"] if m in ids), None)
    return chosen, ids


def rate_headers(headers) -> dict:
    return {k: v for k, v in headers.items() if "ratelimit" in k.lower() or k.lower() == "retry-after"}


def run_once(client: OpenAI, model: str, tool_choice: str = "auto", max_steps: int = 6) -> dict:
    messages: list[dict] = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": ALERT}]
    calls, tools_used, report, error = [], [], None, None
    for step in range(max_steps):
        t0 = time.perf_counter()
        try:
            raw = client.chat.completions.with_raw_response.create(
                model=model, messages=messages, tools=TOOLS, tool_choice=tool_choice, temperature=0.2,
            )
        except APIStatusError as e:
            error = {"step": step, "status": e.status_code, "body": str(e.body)[:500],
                     "headers": rate_headers(e.response.headers)}
            break
        latency = time.perf_counter() - t0
        resp = raw.parse()
        usage = resp.usage
        calls.append({
            "step": step,
            "latency_s": round(latency, 2),
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "headers": rate_headers(raw.headers),
        })
        msg = resp.choices[0].message
        # Keep every field the provider sent back (some, like Gemini thought
        # signatures, must be returned unchanged on the next turn).
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            error = {"step": step, "status": "no_tool_call", "body": (msg.content or "")[:300]}
            break
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            tools_used.append(name)
            if name == "submit_report":
                report = args
                result = json.dumps({"ok": True})
            else:
                result = fake_tool(name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
        if report:
            break
    total_prompt = sum(c["prompt_tokens"] or 0 for c in calls)
    total_completion = sum(c["completion_tokens"] or 0 for c in calls)
    return {
        "llm_calls": len(calls),
        "tools_used": tools_used,
        "report": report,
        "correct": bool(report and report.get("failure_type") == "bad_deploy"
                        and any(ref in str(report.get("culprit", "")) for ref in ("v1.3.0", "a1b2c3d"))),
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "total_latency_s": round(sum(c["latency_s"] for c in calls), 2),
        "error": error,
        "calls": calls,
    }


def check_provider(name: str, runs: int, tool_choice: str = "auto") -> dict | None:
    cfg = PROVIDERS[name]
    key = os.getenv(cfg["key_env"])
    if not key:
        print(f"[{name}] skipped: {cfg['key_env']} is not set in .env")
        return None
    client = OpenAI(base_url=cfg["base_url"], api_key=key, max_retries=0, timeout=60)
    print(f"[{name}] listing models ...")
    model, ids = pick_model(client, cfg)
    print(f"  {len(ids)} models available")
    if not model:
        print(f"  none of the preferred models found. Set {cfg['model_env']} in .env to one of:")
        for m in ids:
            print(f"    {m}")
        return {"provider": name, "models": ids, "model": None}
    print(f"  using model: {model} (tool_choice={tool_choice})")
    results = []
    for i in range(runs):
        r = run_once(client, model, tool_choice)
        results.append(r)
        status = "ok" if r["correct"] else ("ERROR " + str(r["error"]["status"]) if r["error"] else "wrong answer")
        print(f"  run {i + 1}: {status} | llm calls {r['llm_calls']} | tools {r['tools_used']} | "
              f"tokens in/out {r['prompt_tokens']}/{r['completion_tokens']} | {r['total_latency_s']}s")
        if r["error"]:
            print(f"    error detail: {r['error']}")
        if r["calls"] and r["calls"][-1]["headers"]:
            print(f"    rate-limit headers: {r['calls'][-1]['headers']}")
        if i + 1 < runs:
            time.sleep(3)
    return {"provider": name, "base_url": cfg["base_url"], "model": model, "tool_choice": tool_choice,
            "models": ids, "runs": results}


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("providers", nargs="*", default=list(PROVIDERS))
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--model", help="override the model for every provider checked")
    parser.add_argument("--tool-choice", default="auto", choices=["auto", "required"],
                        help="'required' forces a tool call every step (the agent ends only via submit_report)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    any_ran = False
    for name in args.providers:
        if name not in PROVIDERS:
            print(f"unknown provider {name}; choose from {list(PROVIDERS)}")
            return 2
        if args.model:
            os.environ[PROVIDERS[name]["model_env"]] = args.model
        result = check_provider(name, args.runs, args.tool_choice)
        if result:
            any_ran = True
            path = OUT_DIR / f"{name}-{stamp}.json"
            path.write_text(json.dumps(result, indent=2))
            print(f"  saved {path.relative_to(ROOT)}")
    if not any_ran:
        print("No provider keys found. Copy .env.example to .env and add GROQ_API_KEY and/or GEMINI_API_KEY.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
