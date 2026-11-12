# Free-tier LLM provider check

**Date:** 2026-11-12
**Script:** [`scripts/provider_check.py`](../scripts/provider_check.py)

The test sends one small fake incident: a 5xx alert, plus fake `search_logs` and `list_deploys` tools and a `submit_report` tool. The model must gather evidence and then submit the correct culprit (`v1.3.0` / `a1b2c3d`). Each model ran 3 times at temperature 0.2. Raw results are in `data/provider_check/`, which is git-ignored.

## Results

| Provider | Model | tool_choice | Correct report | LLM calls per run | Tokens in/out per run | Time per run |
|---|---|---|---|---|---|---|
| Groq | `openai/gpt-oss-120b` | auto | 1/3 | 3-4 | 1.5k-2.4k / 0.4k | 1.8-3.5 s |
| Groq | `openai/gpt-oss-120b` | required | **3/3** | 3-4 | 1.5k-2.4k / 0.3-0.4k | 2.7-5.2 s |
| Groq | `openai/gpt-oss-20b` | required | **3/3** | 3-4 | 1.5k-2.3k / 0.3-0.4k | 1.3-2.2 s |
| Groq | `qwen/qwen3.8-27b` | required | 0/3 | - | - | - |
| Gemini | `gemini-2.5-flash` | auto | 0/3 | - | - | - |

## What failed and why

- **gpt-oss-120b with `tool_choice=auto`:** in 2 of 3 runs, the model found the right cause but wrote it as plain text instead of calling `submit_report`. With `tool_choice=required`, it called the tool every time.
- **qwen3.8-27b:** Groq rejected its tool calls with `tool_use_failed` because the model misspelled tool and argument names (`search_lo`, `culpret`). It is not usable for the agent.
- **Gemini:** every request returned `403 PERMISSION_DENIED`: "The Gemini API free tier is not available for this project". The key can list models but cannot call them without billing. A key from a personal Google account with a new project might work; this has not been tried.

## Groq free-tier limits (from response headers)

Limits apply to each model separately.

| Limit | Value |
|---|---|
| Requests per day | 1,000 |
| Tokens per minute | 8,000 |

A daily token limit may also apply, but it does not appear in the headers. Check it at console.groq.com/settings/limits.

## What this means for the design

1. **Main model:** `openai/gpt-oss-120b` on Groq, called with `tool_choice="required"`. The loop can then only end through `submit_report`, as the design intended.
2. **Development model:** `openai/gpt-oss-20b`. Its limits are separate, so day-to-day testing does not use up the quota for the reported numbers.
3. **The 8,000 tokens-per-minute limit is the tightest constraint.** The test runs used about 2k input tokens, but a real investigation with larger tool output and 8-12 steps could use 15-30k tokens, which works out to several minutes per run once throttled. The agent loop must:
   - cap tool output
   - shrink old tool results
   - wait for the `x-ratelimit-reset-tokens` time when it gets a 429
4. **Each request must stay well under 8,000 tokens,** because a single request over the per-minute limit is rejected.
5. **Gemini is dropped for now.** The backup for the live demo is the recorded-trace replay.
