# Building OnCall Agent: evidence before actions

OnCall Agent is a local, zero-cost incident investigation project. It takes a
generic checkout-service alert, chooses read-only tools, and writes a report
with source-backed evidence. A human must approve a proposed restart or rollback.

The purpose of this project is to explore whether an adaptive investigation loop
adds value over a fixed evidence collector. It does not claim production-ready
diagnosis accuracy or faster recovery for real engineering teams.

## Start with a system that can actually fail

The target is a small FastAPI checkout service backed by SQLite through
SQLAlchemy's QueuePool. A seeded load generator sends checkout and order-history
requests concurrently. The service writes JSON logs; the generator records
request outcomes; a supervisor records process memory and restart events.

There are three real code failures: a currency-context KeyError, an exhausted
connection pool, and an unbounded request cache. Each is a tagged commit in a
separate sandbox repository. A later metadata-only release is deliberately
irrelevant. Rolling back just that latest release leaves the causal code intact.

The real-process acceptance check verified that each fault produces more than
5% HTTP errors and that reset returns the observed error rate below 1%. Memory
enforcement is a local supervisor limit, not a claim that macOS generated an OOM
event. Exact timing and error counts vary with scheduling and memory pressure.

## Make evidence repeatable

Live systems change while a model is investigating. Evaluation therefore uses
frozen captures: logs, request metrics, RSS samples, events, deployments, health
results, and commit diffs, all anchored to one alert timestamp. The answer key
is stored separately. The model receives the alert and tool results, not the
scenario folder name or the expected label.

Read-only tools work on these captures, bound their output, and report stale
metrics. Log search supports literal words and common field filters. This
detail mattered: an early live run used `service:checkout-api level:error`,
which a substring-only implementation could not interpret. The fixed parser
now supports those filters, and a regression test checks them.

## Let the model choose, but validate the result

The agent records a short public plan, then chooses its tools and arguments.
It can compare deployments, read a code diff, inspect error groups, query metrics,
or retrieve a runbook. The trace records these observable decisions, not private
chain-of-thought. A fixed step limit and duplicate-query guard bound the loop.

The report is a validated schema with a timeline, failure type, culprit,
confidence, evidence, next steps and proposed actions. An unknown diagnosis has
low confidence and no remediation actions. High confidence requires observed
evidence and an added-code citation; it is not a calibrated probability.

Evidence formatting caused real failures during development. Models sometimes
combined JSON fields into a quote that never appeared verbatim. The final
protocol gives each result a tool ID and a menu of source excerpts. The model
selects excerpt IDs; the application copies the actual source text and checks
it again. Compaction preserves these references when older results are shortened.

Groq also rejected some native function-call outputs. Report-format recovery
uses a strict JSON schema over the same collected evidence, then runs the same
report validation. This changes serialization, not the diagnosis or the answer
key. Provider waits and formatting recovery remain visible in the trace.

## Keep remediation separate

The model never receives an executor tool. The dashboard presents a proposed
action for a person to approve or reject. The executor accepts only restart or
rollback to the known healthy release, checks that the capture still matches
the current deployment, and records the human decision before executing.

Duplicate decisions, evaluation fixtures, stale captures and inconclusive
reports cannot authorize changes. After execution, the code checks traffic
outcomes and both health endpoints.

The verified live test identified the pricing release, then executed a rollback
only after explicit human approval. The post-action window contained **135
requests, zero HTTP 5xx responses and zero connection errors**, with both health
checks passing. This is a controlled recovery observation, not a production SLA.

## Test the agentic claim honestly

The baseline collects a fixed set of evidence, including the latest deploy's
diff, then asks the same model for one report. The agent may follow up with a
different diff or query. The grader requires the correct failure type, the
causal release rather than its decoy, and verified evidence.

The measured pilot counts are in [evaluation-results.md](evaluation-results.md),
with raw CSVs under `eval/results/`. In the final main-model bad-deploy trial,
both methods found the cause. Other main-model trials were limited by free
quota. The development model also produced wrong diagnoses. These results do
not establish that the agent is more accurate than the baseline.

The main-model API reported a 200,000-token daily limit during integration.
Requests can also hit the 8,000-token-per-minute limit. A provider may consume
quota on a rejected request without returning token usage. The response cache,
explicit backoff, compact tool results and resumable evaluation help, but they
do not remove this constraint. Paid fallback is deliberately excluded.

## A demo should show its limitations

The Streamlit dashboard runs investigations in background processes, shows
file-backed traces and reports, and keeps approval separate from investigation.
Recorded successful runs are clearly labelled as replays and have no execution
buttons. They provide a useful fallback when the free API is unavailable, without
pretending that a new investigation happened.

The next work is to complete the quota-limited trials, add independent scenario
variants and test citation relevance beyond literal matching. The current grader
checks provenance, not whether every quote logically proves every sentence.

Source for provider-specific output controls: [Groq reasoning documentation](https://console.groq.com/docs/reasoning)
and [structured outputs documentation](https://console.groq.com/docs/structured-outputs).
