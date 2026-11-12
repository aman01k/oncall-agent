# Viva preparation

**What is the project?** OnCall Agent investigates an alert using logs, metrics,
deployments, commit diffs and runbooks, then produces a report with evidence.
Humans approve proposed remediation separately.

**Why is it agentic?** The model chooses the next tool and its arguments based
on previous results. It can follow up on a deployment or reject a decoy. The
sequence is not fixed in Python. The fixed-pipeline baseline provides a comparison.

**What is a tool call?** The model asks for a named operation with JSON arguments.
Python validates and executes an allowlisted read-only function, then returns
the result. Tool descriptions and schemas tell the model what operations exist.

**What does retrieval mean here?** Keyword search ranks six local markdown
runbooks and past-incident notes. A second tool reads a selected guide. No vector
database or embedding service is required for this small collection.

**Why snapshots?** Live evidence changes. A snapshot freezes the data and alert
clock so repeated investigations and the baseline can receive the same evidence.
The model never receives the answer key.

**Why SQLite?** The project runs locally with no Docker or paid infrastructure.
SQLAlchemy's explicit QueuePool still creates real connection contention.
Threaded synchronous database endpoints allow requests to compete concurrently.

**How are the failures created?** Real tagged code changes introduce a missing
currency lookup, an undersized connection pool with a slow query, or retained
request allocations. A later metadata-only deploy is a decoy. Reset checks out
the healthy tag in a separate sandbox repository and restarts the service.

**How do citations work?** Tools expose source excerpt IDs. The model chooses
IDs; the application copies the actual quotes and verifies their provenance.
This prevents invented quote text, but does not prove that every quote logically
supports every sentence. That is a remaining evaluation limitation.

**How is approval enforced?** The model has no executor. Separate code requires
a human decision, an allowlisted action and a snapshot matching the current
deployment. It records the decision before execution and refuses duplicates.
Evaluation fixtures and replays cannot authorize changes.

**What was demonstrated live?** A bad deployment was identified, a human approved
rollback to v1.0.0, and recovery showed 135 requests with no HTTP or connection
errors. Both health endpoints passed. This was a short controlled test.

**Did the agent beat the baseline?** The pilot does not support that claim.
Both methods passed the completed main-model bad-deploy trial. Other trials
were wrong or blocked by free quota. Show the actual results table, including
failures, rather than claiming universal accuracy.

**What would production need?** Authentication, stronger process isolation,
real monitoring integrations, secret redaction, stronger action policies,
larger independent evaluations and a better-tested incident corpus. The current
project is a controlled local demonstrator.

**What changed after the failed pilot?** The new guard connects the named culprit to an inspected service-code diff and a cited changed line from that revision. It rejects the two historical decoy reports offline, but also rejects correct reports without enough proof. Fresh v7 model accuracy remains unmeasured. The baseline now collects all returned recent diffs to meet the same rule fairly.
