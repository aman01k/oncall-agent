# OnCall Agent

An AI agent that investigates a production alert the way an on-call engineer would. It plans its steps, calls tools to gather evidence, and writes a root-cause report with suggested fixes. Any action that changes the system needs human approval first.

> **Status (12 Nov 2026):** core demo implemented and verified: live alert → agent investigation → human-approved rollback → healthy service. Automated tests and all three fault mechanisms pass. Pilot evaluation is published with wrong diagnoses and quota-limited attempts included. Completing the main-model evaluation requires free quota to replenish.

## The problem

When a production service breaks, the on-call engineer spends the first part of the incident collecting context. They read logs, check error-rate graphs, look at recent deploys, and search old runbooks for a similar issue. My estimate is 30 to 60 minutes; I have not checked this against a published source. Small teams and startups without a dedicated SRE recover more slowly, and recovery depends on how experienced the person on call is.

**Target users:** backend and DevOps engineers, on-call developers in small to mid-size teams, and student or startup teams running their own services.

## What it does

1. **Alert intake.** An alert such as `checkout-api 5xx > 5% over 2m` is raised by a manual trigger (a webhook comes later).
2. **Investigation loop.** At each step the model sees all results so far and picks the next tool or stops. No tool order is hard-coded. Tools:
   - search logs
   - query metrics
   - list recent deploys
   - show one commit's diff
   - health check
   - search and read runbooks
3. **Plan and re-plan.** The agent records its plan and hypotheses, and updates them when the evidence disagrees.
4. **Structured report.** The report contains:
   - a timeline
   - the failure type and culprit
   - evidence quoted from real tool output
   - a confidence level
   - next steps
5. **Human approval.** The agent can only *propose* a restart or rollback. A person approves it in the dashboard. Separate code then runs the action and checks that the service recovered.
6. **Trace dashboard.** A Streamlit page shows every step, tool call and result. Recorded runs can be replayed, and they are labelled as replays.
7. **Evaluation.** Three seeded failures run against frozen snapshots and are graded by a script:
   - a bad deploy
   - database connection-pool exhaustion
   - a memory leak

   The agent is compared against a fixed pipeline that collects a fixed set of evidence and asks the model a single question.

## Architecture

```
            alert (manual trigger)
                    │
                    ▼
   ┌─────────────────────────────────┐        ┌───────────────────────────┐
   │ Agent loop (agent/)             │ tools  │ Read-only tools           │
   │  plan → call tool → observe     │───────▶│ (telemetry/)              │
   │  → re-plan → ... → submit_report│        │ logs · metrics · deploys  │
   └──────────────┬──────────────────┘        │ git diff · health ·       │
                  │ writes                    │ runbooks                  │
                  ▼                           └─────────────┬─────────────┘
         runs/<id>/trace.jsonl                              │ reads
         runs/<id>/report.json                              ▼
                  │                           ┌───────────────────────────┐
                  ▼                           │ Checkout service          │
   ┌─────────────────────────────────┐        │ (service/, sandbox repo)  │
   │ Streamlit dashboard (ui/)       │        │ FastAPI + SQLite          │
   │  trace view · report · replay   │        │ JSON logs · metrics.db    │
   │  [Approve] [Reject]             │        │ deploys.json · git tags   │
   └──────────────┬──────────────────┘        └─────────────▲─────────────┘
                  │ on approve                              │
                  ▼                                         │
   ┌─────────────────────────────────┐                      │
   │ Allowlisted executors (actions/)│──────────────────────┘
   │  restart · rollback to tag      │   then re-check health
   └─────────────────────────────────┘
```

**Stack:**
- **Language:** Python.
- **Service and storage:** FastAPI, SQLAlchemy 2 with SQLite.
- **Dashboard:** Streamlit.
- **Model client:** the `openai` Python client pointed at a free LLM tier (Groq or Gemini through their OpenAI-compatible endpoints), with Ollama as an optional local backup.
- **Not used:** Docker and paid services.

## Why this is an agentic AI project

- **The model chooses the path.** Every step, it decides which tool to call and with what arguments, based on what it has seen so far.
- **The plan can change.** The plan is explicit state, and changes to it are recorded in the trace.
- **Retrieval.** The agent searches runbooks and past incidents to compare the issue with known fixes.
- **Human in the loop.** Approval is enforced in code, not in the prompt. The model never gets an executor.
- **The claim is tested.** The evaluation compares the agent against a fixed pipeline with the same model, tools and token budget. Any result is reported as it is, including a tie or a loss.

## Progress

Weights add up to 100%. The items marked **demo** add up to the 70% that will be shown live on 19 Nov.

| # | Item | Weight | Done when | Demo | Status |
|---|---|---|---|---|---|
| 1 | Checkout service, 3 faults, load generator, `devctl` | 15% | Each fault pushes 5xx above 5% within 2 min; `reset` brings it below 1% | demo | done: all three mechanisms and reset verified |
| 2 | Read-only telemetry tools | 10% | Tools work on live data and on snapshots, with output caps and tests | demo | done: frozen tools, clock handling and output caps |
| 3 | Agent loop and report schema | 20% | One scenario passes 3/5 runs end to end | demo | implemented: main-model and live bad-deploy reports pass; 3/5 robustness goal pending |
| 4 | Runbook search | 5% | 5-10 runbooks searchable; the agent cites them | demo | done: six runbooks/past-incident guides and search |
| 5 | Approval gate and executors | 10% | Approve runs restart/rollback in the sandbox, then a recovery check | demo | done: explicitly approved live rollback and health/error recovery verified |
| 6 | Trace dashboard and replay | 10% | Live trace, report view, labelled replay | demo | done: auto-refreshing dashboard and labelled real replays |
| 7 | Snapshot evaluation, grader, baseline | 15% | Results table for agent vs baseline committed | | partial: pilot CSVs published; further trials blocked by free quotas |
| 8 | Webhook intake | 5% | `POST /alerts` starts a run | | done: local webhook and bounded queue tested |
| 9 | Documentation and technical blog | 10% | Blog submitted | | drafts ready: demo, evaluation, blog and viva notes; submission pending |

## Milestones

| Date | Goal |
|---|---|
| 12 Nov | Repo public, design brief, LLM quota measured, minimal service |
| 13 Nov | All three faults reproducible with load; reset works |
| 14 Nov | Tools, snapshots, runbooks, grader |
| 15 Nov | Agent loop; one scenario passes 3/5 (midpoint check) |
| 16 Nov | Baseline and evaluation harness; dashboard started |
| 17 Nov | Dashboard with approval and replay; prompts frozen; first full evaluation |
| 18 Nov | Second evaluation batch; rehearsals; recorded fallback |
| **19 Nov** | **Project assessment (live demo)** |
| **20 Nov** | **Submission with final evaluation results** |
| **22 Nov** | **Technical blog** |

## Repository layout

```
service/      checkout service (code is bootstrapped into a git-ignored sandbox repo)
telemetry/    read-only tools: logs, metrics, deploys, git, health, runbooks
agent/        agent loop, LLM client, schemas, trace writer
actions/      allowlisted remediation executors (restart, rollback)
ui/           Streamlit dashboard
eval/         answer keys, snapshot fixtures, grader, baseline, results
runbooks/     markdown runbooks and past incidents
scripts/      devctl, load generator, bootstrap scripts
traces/       recorded traces for replay
tests/        tests
docs/         design brief, decision log, evaluation method, demo script
```

## Getting started

Prepare the environment (Python 3.14):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your own free-tier API key
```

Run the checkout service. Logs go to `data/logs/service.jsonl`:

```bash
python -m uvicorn service.app:app --port 8001 --no-access-log
```

Checks:

```bash
python -m pytest -q                      # service, agent, approval and interface tests
python scripts/pool_check.py             # confirms connection-pool exhaustion under 20 concurrent requests
python scripts/scenario_check.py         # checks all three real faults and resets (about 2 min)
python scripts/provider_check.py groq --tool-choice required --runs 3   # free-tier model check
```

## Run the failure lab

```bash
python scripts/devctl.py up
python scripts/devctl.py inject bad_deploy
python scripts/devctl.py check --seconds 15
python scripts/devctl.py reset
python scripts/devctl.py down
```

The other scenarios are `pool_exhaustion` and `memory_leak`. See [the lab guide](docs/local-lab.md) for tagged releases, metrics, memory limits and recovery checks.

## Investigate an incident

```bash
python -m streamlit run ui/dashboard.py --server.address 127.0.0.1
```

Open the local dashboard, inject a fault, then capture the alert and start an
investigation. Review the report before approving a rollback. The agent runs in
a separate process; model-selected tools and plans are recorded in a trace.

For a frozen scenario:

```bash
python -m agent.runner eval/fixtures/bad_deploy --model openai/gpt-oss-20b
python -m eval.evaluate --model openai/gpt-oss-120b --runs 1
python scripts/record_replays.py
```

See the [demo guide](docs/demo.md), [evaluation method](docs/evaluation.md) and
[local lab guide](docs/local-lab.md). API keys stay in `.env`; the free provider
may pause investigations when quota is tight. Replays are labelled explicitly.

## Non-goals

- Not production-ready. One simulated service, with synthetic data only.
- No automatic remediation. Every change needs human approval.
- No Docker, Kubernetes, Prometheus or Grafana.
- No claims about recovery time for real teams. The evaluation measures diagnosis accuracy on a controlled service.

## Prior art

Similar tools exist, and this project does not build on them:
- HolmesGPT (Robusta) and k8sgpt, which are open source
- AI investigation features in commercial incident tools

This project differs in being small and local-first, evaluated against decoy signals and a fixed baseline, and having a code-enforced approval gate.

## Documents

- [Design brief](docs/concepts_brief.md)
- [Decision log](docs/decisions.md)

## Current validation and submission notes

- 36 automated tests pass.
- Real fault checks cover bad deploy, pool exhaustion and memory leak.
- Human-approved live recovery: 135 requests, zero HTTP 5xx, zero connection errors, both health probes pass.
- [Pilot results](docs/evaluation-results.md) include all final-experiment attempts, including wrong diagnoses and quota failures.
- [Technical blog draft](docs/technical-blog.md) and [viva notes](docs/viva-notes.md) explain the build and its limitations.
- Replays are selected successful real investigations; they are never presented as fresh runs or benchmark averages.

## Offline follow-up

Known diagnoses must now name an inspected revision and cite its changed service Python code, alongside observed symptoms. The same rule applies to a strengthened fixed collector. These structural checks do not establish semantic causality or improved diagnosis accuracy.

- [Historical failure audit](docs/offline-review.md): five real completed reports, no new model calls.
- [Presentation notes](docs/presentation-notes.md): ten slides and a seven-minute speaking plan.
- `python scripts/rehearse.py`: verifies saved real replay evidence and approved recovery without API calls or system changes.
- Future model runs use `--experiment v7`; v6 remains frozen.
