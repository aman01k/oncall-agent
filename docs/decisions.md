# Decision log

Each entry records a design decision, the date it was made, and the reason. Newer entries go at the bottom.

## 2026-11-12: Plain Python processes, no Docker

All parts run as local Python processes.
- **Database:** SQLite through SQLAlchemy instead of Postgres.
- **Restart:** a small supervisor script.

**Reason:** Docker is not installed, it would compete for RAM on a 16 GB Mac, and learning it would cost a day out of a 7-day schedule.

## 2026-11-12: Free LLM tier through one OpenAI-compatible client

The agent uses the `openai` Python package. Groq, Gemini or Ollama is selected by `base_url`, model and key in `.env`. The provider for the reported numbers will be chosen after measuring free-tier quota.

**Reason:** zero-spend constraint. One client avoids three code paths.

## 2026-11-12: Hand-written agent loop, no framework

No LangGraph, CrewAI or other agent framework.

**Reason:** less setup time. The loop is also the part that makes the project agentic, so it should be visible and easy to explain.

## 2026-11-12: Evaluate on frozen snapshots, graded by a script

Each scenario is captured into `eval/fixtures/<scenario>/<variant>/` with a fixed alert time. Tools read from a data-source folder. A script grades reports:
- exact failure type
- an accepted culprit reference
- every evidence quote must be an exact substring of real tool output

**Reason:** live runs cannot be repeated or compared. An LLM judge uses quota and gives different answers on reruns.

## 2026-11-12: Agent vs fixed-pipeline baseline

The baseline uses the same model, tools and token budget, calls each tool once with default arguments, and gets no follow-up queries. Scenarios are designed so the failure type is visible early, but naming the culprit needs follow-up queries. Results are reported as they come out, including a tie or a loss.

**Reason:** this tests whether the agent loop adds anything over a single prompt.

## 2026-11-12: Checkout service lives in a separate sandbox repo

The service code is bootstrapped into `sandbox/checkout-service/`. That folder is a separate git repo, ignored by this one, with one tagged commit per fault. Rollback checks out a tag there.

**Reason:** a rollback inside this repo would revert the agent code and add fake commits to the project history.

## 2026-11-12: Two-phase approval, enforced in code

The agent only proposes actions (restart, or rollback to a named tag). After a human approves in the dashboard, an allowlisted executor runs the action, then re-checks health and the 5xx rate.

**Reason:**
- Streamlit cannot pause a running loop for a button click.
- A gate written only into the prompt is not a gate.

## 2026-11-12: One JSONL trace per run

The live view, replay, grader, evaluation table and blog figures all read the same versioned trace file. The schema will be frozen by 15 Nov.

**Reason:** one source of truth, and the demo fallback is the same file a live run writes.

## 2026-11-12: Python 3.14

The project uses the Python 3.14 already installed on the development Mac. A clean virtual environment installed and imported every dependency in `requirements.txt` without errors. The exact versions are recorded in `requirements.lock.txt`.

**Reason:** installing a second Python version would cost time and add nothing.

## 2026-11-12: Groq gpt-oss-120b with tool_choice=required

- **Main model:** Groq `openai/gpt-oss-120b`, called with `tool_choice="required"`.
- **Development model:** `openai/gpt-oss-20b`, which has separate limits.
- **Gemini:** dropped for now.

**Reason:** see [provider_check.md](provider_check.md).
- With `tool_choice=required`, both gpt-oss models submitted the correct report 3/3 times. With `auto`, the 120b model wrote its answer as plain text in 2 of 3 runs.
- Qwen produced malformed tool calls.
- Gemini returned 403 because its free tier is unavailable for this project.
- Groq's limit of 8,000 tokens per minute per model means the agent loop must keep requests small.

## 2026-11-12: Reproducible local failure lab

- Each fault has a causal release and a later metadata-only decoy in the separate sandbox repo. Both releases actually run and are recorded in deploy history.
- Traffic is seeded, rate-limited and bounded to 24 concurrent requests. Transport failures are reported separately from HTTP errors.
- The memory fault retains touched random bytes and returns overload HTTP 503 after 96 MiB retained; the supervisor enforces a 192 MiB RSS limit and records its own kills explicitly.
- Request telemetry and supervisor RSS/events share a separate WAL-mode metrics database; the request telemetry currently covers the generated traffic.
- Log IDs include a process prefix to remain unique across restarts. Process state includes creation time to reject stale/reused PIDs.

**Reason:** all three faults need real, observable evidence and reliable recovery before the read-only tools and agent can be built. The small memory cap bounds local resource use. A restart delays a leak; rollback removes its code. See [local-lab.md](local-lab.md).

## 2026-11-12: Evidence references and report-format recovery

The model selects tool/excerpt IDs; application code copies source text into the final report and verifies it. Older results retain their citation menus when compacted. If native report function calls fail, strict JSON output writes the same model report over the same evidence. Unknown diagnoses have low confidence and no actions. A known diagnosis needs an observed log or metric citation.

**Reason:** actual integration runs exposed malformed function arguments and reconstructed quotes. A formatting failure must not silently turn into fabricated evidence. Source IDs avoid that error without supplying the correct diagnosis.

## 2026-11-12: Live approval and recovery verified

The live report identified the currency-context release. aman01k explicitly approved rollback in chat. The executor recorded that decision, rolled the sandbox back to v1.0.0, then observed 135 requests with zero HTTP 5xx and zero network errors. Both health probes passed.

**Reason:** the approval gate should be exercised beyond unit tests, while preserving the human decision in the trace. This short observation is not a production recovery claim.

## 2026-11-12: Preserve quota-limited pilot outcomes

Both free Groq models reached their daily quotas during development/evaluation. The main model reported a 200,000-token daily limit. v6 pilot CSVs retain wrong diagnoses and quota failures separately; no paid fallback is used. Failed attempts can be archived and resumed from cached prefixes after quota replenishes. Completed wrong diagnoses are never retried by --retry-failed.

**Reason:** hiding failed runs or calling cached resumes independent trials would make the evaluation misleading. The fixed baseline collects six predefined results, including a runbook search and the latest deploy diff; it does not adaptively read additional guides or diffs. Claims are limited to that collector. Provider-specific output settings follow [Groq reasoning](https://console.groq.com/docs/reasoning) and [structured output](https://console.groq.com/docs/structured-outputs) documentation.
