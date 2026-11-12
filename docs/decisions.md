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
