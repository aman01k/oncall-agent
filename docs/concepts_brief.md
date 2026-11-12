# OnCall Agent

* **Author:** aman01k
* **Date:** 2026-11-12

## Overview

When a production service breaks, the on-call engineer spends the first part of the incident collecting context. They read logs, check error-rate graphs, look at what was deployed recently, and search old runbooks. The author estimates this takes 30 to 60 minutes; no external source has been checked for this figure yet. Small teams without a dedicated SRE recover more slowly, and the result depends on how experienced the person on call is.

OnCall Agent takes an alert such as "checkout-api 5xx rate above 5% over 2 minutes". It investigates the way an engineer would: it writes a plan, calls tools to collect evidence, changes the plan when the evidence disagrees, and produces a root-cause report. The report contains a timeline, the likely cause with cited evidence, a confidence level, and next steps. The agent can only *propose* a restart or rollback. A human must approve it, and separate code then carries it out.

**Target users:** backend and DevOps engineers, on-call developers in small teams, and student or startup teams running their own services.

**Project constraints:** solo developer, about 5-6 hours a day, Python, a 16 GB Mac with no Docker, no money spent. Deadlines:
- 12 Nov: public GitHub repo shared
- 19 Nov: live demo with at least 70% complete
- 20 Nov: submission
- 22 Nov: technical blog

The developer must be the only contributor on the repo.

**Why this counts as agentic AI:** at each step the model sees all results so far and picks the next tool or stops. No tool order is hard-coded. The project proves this by comparing the agent against a fixed pipeline (call every tool once, then one prompt) on the same model, tools and token budget.

### System at a glance

| Part | What it is |
|---|---|
| Target service | A small FastAPI "checkout" service run as a plain local Python process (port 8001, no reload, no workers). Its code lives in a separate, git-ignored sandbox repo with tagged versions. |
| Faults | Three real commits and tags in the sandbox repo: a bad deploy (`KeyError` on about 30% of `/checkout` calls), connection-pool exhaustion (pool shrunk plus a slow `/orders/history` query), and a memory leak (unbounded cache). Each scenario also has a decoy deploy that is not the cause. |
| Traffic | `loadgen.py` sends 5-20 requests per second with 10+ in flight, using a fixed random seed. |
| Telemetry | JSON-line logs; `app.db` and `metrics.db` as separate SQLite files in WAL mode; `deploys.json`; the sandbox repo's git history. All times are UTC ISO-8601. |
| Supervisor | A small long-running script with a PID file. It starts and restarts the service, samples memory (RSS), and kills the service above a hard memory cap, logging this like an out-of-memory kill. |
| Agent | A hand-written tool-calling loop using the `openai` Python package. The provider is switched by `base_url`, model and key in `.env` (Groq or Gemini, with Ollama as an optional backup). |
| Tools | Search logs, query metrics, list recent deploys, `git_show(sha)` for one commit's diff, health check, search runbooks, read one runbook, `update_plan`, `submit_report`, `propose_action`. All tools are read-only. |
| Approval | Two phases. The agent finishes and writes `report.json` with proposed actions. An Approve or Reject button then calls a fixed allowlist of executors (restart, or rollback to a named tag). |
| Trace | One append-only JSONL file per run. The live view, replay, grader, evaluation table and blog figures all read only this file. |
| Dashboard | Streamlit. It only reads trace files and calls the approval executor. It never runs the agent loop inside a page rerun. |
| Control | `devctl` with `up`, `down`, `inject <scenario>`, `reset`, `capture`, `check`. |

## Analysis

Seven review lenses examined the concept: design, technical accuracy, simplicity, readability, implementation readiness, document structure, and inventive problem solving. Their findings are grouped below, starting with the most serious.

### 1. The evaluation could fail to show anything (highest risk)

**The baseline may tie the agent.** With three small scenarios, a fixed pipeline that calls every tool once puts all the evidence in front of the model, and a capable model will diagnose about as well as the agent loop. If that happens, the project's main claim fails. Weakening the baseline on purpose would be rigging and would be noticed.

*Response:* design each scenario so the **type** of failure is visible on the first look, but naming the **culprit** needs 2-3 follow-up queries whose arguments come from earlier results. Examples: reading one commit's diff with `git_show(sha)`, latency for one endpoint, or fetching specific log lines by ID. The baseline gets the same model, tools and token cap, but calls each tool once with default arguments and has no `git_show`. Its code is published. The hypothesis is written down before any runs, and a tie or a loss gets reported as it is. "Same accuracy at three times the tokens" is still a valid result for the blog.

**Live evaluation runs cannot be compared or repeated.** Each live run would produce different timestamps, traffic and leftover log lines, so model variance gets mixed up with data variance.

*Response:* `devctl capture` freezes logs, metrics, deploys, git history with diffs, and an `alert.json` with a fixed `fired_at` time into `fixtures/<scenario>/<variant>/`. Every tool takes a data-source folder and computes time windows from `fired_at`, never the wall clock. Evaluation uses snapshots only. The live service is for the demo and for remediation.

**The answer can leak into the data.** The same person writes the faults, logs, runbooks and answer key. A runbook titled "Connection pool exhaustion" with matching symptoms, a fault flag in the startup logs, or a commit message like "add leaky cache" would let both systems pass and make the comparison meaningless.

*Response:*
- Runbooks list symptoms, then checks, then several possible causes, including near-misses and at least one runbook that points toward each decoy.
- The fault switch never appears anywhere a tool can read.
- Commit messages stay neutral.
- `leak_check.py` greps every snapshot for answer-key strings.
- Tools cannot read the `eval/` folder.
- SQLAlchemy's real error text ("QueuePool limit ... reached") stays, because it is realistic. It reveals the failure *type*, but the culprit is the *commit* that caused it.

**The pass rule has to be decided by code.** The agent ends every run by calling `submit_report`, whose arguments must match a fixed schema:
- `failure_type`, chosen from a list that includes distractors (`config_error`, `dependency_outage`, `traffic_spike`, `unknown`)
- `culprit` (kind and reference)
- `evidence[]` (source, ID, exact quote)
- `confidence`, `timeline`, `next_steps`, `proposed_actions`

A script grades each report:
- exact match on `failure_type`
- the culprit matches an accepted reference in `eval/answer_keys.yaml`
- every quoted piece of evidence is an exact substring of real tool output, because models invent plausible log lines

No LLM judge is used.

**Small sample.** Five runs per scenario move the pass rate in 20-point steps.
- Report counts ("4/5"), not percentages, and claim no statistical significance.
- Use one model for the reported numbers.
- Record the model ID, temperature (0.2-0.3) and prompt version on every row.
- Freeze prompts before the final runs.
- Get variety from snapshot variants: easy (no decoy), hard (decoy), and hard with the decoy's timing shifted.
- Report each outcome as correct, decoy blamed, or other wrong.

**Claim only what is measured.** The evaluation measures diagnosis accuracy with verified evidence on a controlled service. It does not measure recovery time for real teams. Report seconds per report as a side number, and treat "faster recovery" as a hypothesis.

### 2. Free-tier quota limits what can run

The loop sends the whole conversation again on every step, so an uncapped run can use tens of thousands of input tokens. Free-tier limits on Groq and Gemini are tight, and they changed during 2025. The figures the reviewers recalled are unverified, and some may be out of date. Quota, not features, may decide how many runs fit in a day.

*Response:*
- Today, run 20 tool-calling requests on each provider. Log the token usage, rate-limit headers and any 429 errors, and read the limits on each provider's console.
- Choose the evaluation provider by measured quota.
- Cap each run at 8-12 steps with a token budget. Cap each tool result at about 4,000 characters, with a "N more lines truncated" marker.
- Tools return summaries: errors grouped by type with the top few lines and their IDs, and metric min, max, p95 and when the change started.
- Shrink old tool results in the history to one line each.
- Cache LLM responses on disk, keyed by a hash of the request, so reruns are free and an interrupted batch can resume.
- Honour retry-after headers.
- Spread evaluation over 16-18 Nov so the daily quotas reset between batches.

**One client, not three adapters.** Groq, Gemini and Ollama all offer an OpenAI-compatible endpoint, so the `openai` package with a different `base_url` covers all three. Check today that Gemini tool calling works over that endpoint for three turns in a row. Gemini's thinking models can fail on the second turn if the history drops their attached data. Groq returns a `tool_use_failed` error on malformed tool JSON; catch it and retry up to twice. Read the model IDs from each provider's API today and keep them in config.

**Ollama is a weak backup.** 7-8B models often produce malformed tool calls. Ollama's default context window is small and silently drops older content. It also competes for memory with the leaking service. The recorded-trace replay is the main fallback. Ollama is kept only if it passes one full scenario by 17 Nov (`qwen2.5:7b-instruct` or `qwen3:8b`, context set to about 16k).

### 3. The simulated service must actually fail as intended

- **No traffic means no failure.** There is no 5xx rate, latency, pool contention or leak without concurrent requests. `loadgen.py` is required. The acceptance test for each scenario: after `inject`, 5xx goes above 5% within 120 seconds; after `reset`, it stays below 1%.
- **Pool exhaustion needs exact settings:**
  - plain `def` endpoints (not `async def`), so FastAPI runs them on its 40-thread pool
  - SQLAlchemy 2.x with an explicit `QueuePool` on a file database
  - `pool_size=2, max_overflow=0, pool_timeout=2`
  - the slow query held with a read plus `time.sleep(3)`
  - a client timeout of 10 seconds or more

  Check today that 20 concurrent requests produce `TimeoutError` in the log.
- **Separate SQLite files** for app data and metrics, both in WAL mode, so the two do not lock each other. Tools open them read-only.
- **Metrics must survive a hang.** The supervisor writes RSS and restart events. The app writes request counts and pool use. The metrics tool reports when the last sample was taken, and says when data is stale.
- **The memory leak needs extra handling on macOS.** macOS has no Linux-style out-of-memory killer, and zero-filled memory may not raise RSS at all.
  - Leak `os.urandom` chunks of 2-5 MB per request.
  - Return 503 above a soft limit of about 500 MB.
  - Have the supervisor kill the process above about 850 MB and log it as an out-of-memory kill.

  If the leak is unstable by 13 Nov, demo it from its snapshot.
- **One alert for all three scenarios** (`checkout-api 5xx > 5% over 2m`). A separate alert per scenario would give away the failure type. A button checks the threshold against the metrics, so the alert text is not typed by hand.
- **Time and processes.**
  - Use UTC everywhere.
  - The bootstrap script sets git commit dates to match `deploys.json`.
  - Avoid ports 5000 and 7000, which macOS AirPlay uses.
  - Use two health endpoints: `/health` (no database) and `/health/db` (1-second timeout).
  - Middleware adds a `request_id` to every log line.

### 4. Remediation and approval

- **Rollback must not touch the project repo.** A `git checkout` of an old tag in the main repo would revert the agent and dashboard code and add fake commits to the history being graded. The checkout service lives in `sandbox/checkout-service/`, a separate repo that the main repo ignores. Rollback runs `git -C sandbox/... checkout --detach <tag>`, then a restart. After a rollback, `git status` in the main repo must show no changes.
- **The action must fix the real fault.** A restart only delays a memory leak. It does not fix pool exhaustion while the bad commit is still deployed. If the decoy is the latest deploy, "roll back one version" undoes the decoy and leaves the culprit in place. So:
  - Each proposal names a target tag, checked against `git tag --list`.
  - The approval screen shows the current and target tags.
  - After the action, the health check and 5xx query run again, and the report records "recovered" or "not recovered".
  - Nothing retries automatically.
- **Streamlit cannot pause a running loop for a button click.** Every click reruns the whole script, so the approval works in two phases:
  - **Phase 1:** the agent runs to completion in a separate process or thread and writes the trace and report.
  - **Phase 2:** Approve calls the executor and appends the decision and result to the trace.

  Streamlit only reads files, and background threads never call Streamlit functions.
- **Enforce the gate in code.** The model only proposes actions and never holds an executor. Executors accept allowlisted values only, never free text or shell commands, and log who approved and when. Log lines can carry text that tries to instruct the model (prompt injection); the code-enforced gate is the mitigation for that, and tool output is wrapped in clear markers in the prompt.

### 5. Making the agent's behaviour visible

- The plan is real state. An `update_plan(steps, reason)` tool records each plan change, or each hypothesis is marked open, supported or rejected. The trace shows old and new plans side by side.
- The demo includes a moment where the agent rules out the decoy with evidence.
- The evaluation counts re-plans and rejected hypotheses per run.
- **Loop guards:**
  - The run stops only through `submit_report`.
  - At step N-1 the agent is forced to submit, with `failure_type="unknown"` if it has no answer.
  - Repeating a tool call with the same arguments is blocked.
  - Invalid arguments get a validation error back as the tool result, with at most 2 failures in a row.
  - On errors, the UI shows a readable message and a partial "inconclusive" report, never a stack trace.
- **Confidence** is low, medium or high, tied to a rule. For example, high requires two independent verified citations that agree. The evaluation reports pass rate by confidence level.
- **Replay must not look faked.**
  - Every replay shows a banner: "REPLAY: recorded at time T with model M", linked to its evaluation run.
  - Stronger option, a half-replay: cache LLM responses while the tools still run for real against the snapshot, with a LIVE or CACHED badge on each step.
- The trace text is labelled "model-written rationale", not "reasoning".

### 6. Schedule and scope

The implementation-readiness lens estimates about 36 hours of work against 35-40 hours available. That leaves almost no slack.
- A midpoint check on 15 Nov: one scenario passes 3/5 end to end.
- "70% complete" needs a weighted completion table in the README, shown on the first demo slide.

**Cut order if time runs short:**
1. Ollama
2. runbooks beyond 5-6
3. dashboard polish and live streaming (show the trace after the run instead)
4. scenario variants
5. real git versions (fall back to versions in a config file)

**Never cut:** snapshots, report schema and grader, trace and replay, approval gate, trace view.

### Core trade-offs and how the design resolves them

| Trade-off | Resolution |
|---|---|
| A more reliable demo (replay) makes the agent look less real. | Half-replay with LIVE or CACHED badges, and a visible replay banner. |
| More evaluation runs do not fit free-tier quota or the days left. | Compact tool output, step and token caps, a response cache, batched runs. |
| Harder scenarios lower the pass rate and risk the demo. | Hide information rather than make it ambiguous; difficulty tiers per variant. |
| More agent steps cost more without helping when everything fits in one prompt. | Evidence must be pulled with follow-up queries; equal-budget baseline. |
| Realistic live faults cannot be reproduced. | Separate producing evidence (live service) from investigating it (frozen snapshots). |
| Richer evidence uses more tokens and leaks answers. | An evidence boundary checked by `leak_check.py`. |

**Ideal end state:** every investigation writes one append-only JSONL trace against a frozen snapshot. That one file is the live view, the demo fallback, the evaluation record (graded by a script, with every citation checked), the input to approval, and the source of the blog figures. It needs no extra infrastructure and no LLM judge. The demo cannot fail outright, because the fallback is the same file a live run writes.

## Goals vs. Non-Goals

* **In-Scope Goals:**
  * Manual alert trigger (one generic alert, threshold checked against metrics).
  * Agent loop with these tools: log search, metrics query, recent deploys, `git_show`, health check, runbook search and read, `update_plan`, `submit_report`, `propose_action`.
  * Structured report with a timeline, failure type, culprit, verified evidence, rule-based confidence and next steps.
  * Human approval before restart or rollback, enforced in code, followed by a check that the service recovered.
  * Streamlit trace view, with replay of recorded runs.
  * Three scenarios you can trigger, each with a decoy and an acceptance test.
  * Snapshot-based evaluation of the agent against a fixed-pipeline baseline, graded by script (preliminary counts on 19 Nov, full counts on 20 Nov).
  * Public repo with README, completion table, milestone plan, decision log, and the developer as the only contributor.
* **Out-of-Scope Non-Goals:**
  * Production readiness, multiple services, real customer data.
  * Remediation without human approval, or remediation through free-text shell commands.
  * Webhook intake before 19 Nov (planned later, about an hour of work).
  * Embedding-based retrieval (keyword or BM25 search is enough for 5-10 runbooks).
  * Docker, Kubernetes, Prometheus or Grafana.
  * Claims about recovery time for real teams, or statistical significance.

## Alternatives Weighed

| Alternative | Why it was rejected |
|---|---|
| LangGraph, CrewAI or a multi-agent framework | Rejected by author: the setup time does not fit a 7-day solo schedule, and these frameworks hide the loop that makes the project credibly agentic. |
| Docker with Postgres, Prometheus and Grafana | Rejected by author: Docker is not installed, it competes for RAM on a 16 GB Mac, and learning the stack costs days. |
| Paid LLM API (Claude, GPT) | Rejected by author: zero-spend constraint. |
| Ollama as the main model | Rejected by author: 7-8B models are unreliable at multi-step tool calling and have a small default context. Kept only as an optional backup. |
| Separate adapters for Gemini, Groq and Ollama | Rejected by author: three code paths to debug. One OpenAI-compatible client covers all three. |
| Running the evaluation live against the service | Rejected by author: not repeatable, slow, quota-bound, and cannot resume. Snapshots are used instead. |
| LLM-as-judge grading | Rejected by author: uses quota, gives different answers on reruns, and shares the model's biases. Script grading is used instead. |
| Fully scripted or canned demo | Rejected by author: removes the agentic claim. A labelled replay is used only as a fallback. |
| Weakening the baseline or simplifying scenarios to raise the score | Rejected by author: a strawman comparison that reviewers would notice. |
| Fault switches as environment flags only | Rejected by author: the bad deploy would not exist in git history, so rollback would change nothing. Faults are real tagged commits instead. |
| Rollback inside the project repo | Rejected by author: it rewrites the working tree and adds fake commits to the graded history. A separate sandbox repo is used. |
| Pausing the agent loop inside Streamlit for approval | Rejected by author: it breaks under Streamlit's rerun-on-click model. Two-phase approval is used. |
| App data, metrics and traces in one SQLite file | Rejected by author: lock contention would add errors during faults. |
| A different alert text per scenario | Rejected by author: it gives away the failure type. |
| Using HolmesGPT or k8sgpt as the base | Rejected by author: the course asks for an original build. They are cited as prior art in the README and blog. |

## Key Decisions & Staging for Next Steps

**Decisions carried into the design:**
1. Evaluation runs only on frozen snapshots, with a fixed `fired_at` time.
2. Reports are a fixed schema submitted through `submit_report`. A script grades them, with exact-substring checks on every citation.
3. Scenarios reveal the failure type early and need follow-up queries to name the culprit. The baseline uses the same model, tools and budget, and its code is published.
4. One OpenAI-compatible client. The provider for the reported numbers is chosen by quota measured on 12 Nov.
5. The checkout service lives in a git-ignored sandbox repo with real tagged commits for each fault.
6. Two-phase approval: the agent only proposes, and an allowlisted executor acts after a click, followed by a recovery check.
7. One versioned JSONL trace drives the live view, replay, grader and blog. The schema is frozen by 15 Nov.
8. Commits are authored only by the developer, with no co-author lines.

**Open questions for the author:**
- Python version: the reviewers suggest pinning 3.12. The Mac has 3.14.10. Use 3.14 if a clean install of every dependency works today; otherwise install 3.12 from python.org.
- Should the memory-leak scenario run live in the demo, or from its snapshot? Decide on 13 Nov.
- Is there a course rubric to map the completion table to?

**Plan by day:**

| Date | Work | Done when |
|---|---|---|
| Thu 12 Nov | Public repo with `.gitignore` (`.env`, `data/`, `runs/`, `sandbox/`, `*.db`), `.env.example`, README (objective, architecture, completion table, milestones, non-goals), `docs/decisions.md`. Provider smoke test: a 3-turn tool loop on Groq and Gemini, logging tokens and limits. Check that 20 concurrent requests exhaust the pool. Minimal service with JSON logging. | Repo public; quota numbers recorded |
| Fri 13 Nov | Load generator, `devctl`, sandbox repo bootstrap with tags, `metrics.db`, supervisor with memory cap, restart and rollback functions. | All three faults pass their acceptance test |
| Sat 14 Nov | Read-only tools with a data-source folder and output caps, plus tests. Snapshot capture and `leak_check.py`. 5-10 runbooks. Answer keys and grader, with tests. | Grader passes on hand-written reports |
| Sun 15 Nov | Agent loop (tested with a scripted fake model first, then a real one), `update_plan`, `submit_report`, trace writer. Command-line runs on all three snapshots. Freeze trace schema. | One scenario passes 3/5 |
| Mon 16 Nov | Baseline and evaluation harness (CSV output, 429 backoff). First small evaluation pass; fix tools and prompts. Start the Streamlit trace viewer. | Baseline runs on all snapshots |
| Tue 17 Nov | Streamlit: trigger, live trace, report, approval and executor, replay. Freeze prompts. First full evaluation batch. Keep or cut Ollama. | Full demo flow works once |
| Wed 18 Nov | Second evaluation batch. Two or three full rehearsals. Record replay traces and a backup video. `devctl check`. README updated with preliminary numbers. | Rehearsal passes without help |
| Thu 19 Nov | `devctl check`, then the demo. Fill any missing evaluation runs in the evening. | Demo done |
| Fri 20 Nov | Results table (pass counts, decoy blamed, tool calls, tokens, latency, agent vs baseline) and CSV in the repo. Submit. | Submitted |
| Sat 21 – Sun 22 Nov | Blog: architecture, one annotated trace showing a re-plan, results and their limits, failure cases. | Blog submitted |

**Suggested repo layout:** `service/`, `telemetry/` (read-only tools), `agent/` (loop, LLM client, schemas, trace), `actions/` (executors), `ui/`, `eval/` (answer keys, fixtures, grader, baseline, results), `runbooks/`, `scripts/` (`devctl`, `loadgen`, bootstrap), `traces/recorded/`, `tests/`, `docs/` (design, evaluation method, demo script, decisions, blog outline).
