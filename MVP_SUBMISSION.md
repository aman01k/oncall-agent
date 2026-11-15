# OnCall Agent: MVP submission

Repository: https://github.com/aman01k/oncall-agent

## Submission scope

This submission is a local incident-investigation prototype. The assessed demo focuses on a checkout-service bad deployment: alert intake, evidence collection, model-selected investigation tools, a structured report, and human review of a proposed rollback.

The repository also includes three fault mechanisms, runbook retrieval, a local webhook, a dashboard, recorded real investigations and a pilot evaluation. These additional components do not imply that diagnosis is fully validated on every scenario.

## What can be demonstrated

- A FastAPI checkout service with synthetic traffic and observable failures.
- Read-only log, metric, deployment, commit-diff, health and runbook tools.
- An agent that selects tools rather than following a fixed collection order.
- A report containing a timeline, likely cause, confidence, evidence and next steps.
- A separate human-approval executor, restricted actions and recovery checks.
- A dashboard with public plans, tool results and explicitly labelled replays.

The previously verified human-approved rollback observed 135 requests, zero HTTP 5xx responses, zero connection errors and successful health probes. That is a historical, short controlled observation rather than a production guarantee.

## Pre-submission verification, 16 November 2026

- 36 automated tests passed in offline mode.
- All three saved real replay recordings passed evidence-integrity checks.
- A fresh Groq `openai/gpt-oss-120b` v7 investigation correctly diagnosed the bad-deploy snapshot.
- The new report passed both quote verification and named-revision causal-code proof.
- The run used six uncached model responses and took approximately 57 seconds.
- The evidence was a frozen synthetic capture. This was a fresh model investigation, not a newly injected live incident, and no remediation ran during this check.

This validates one submission demo path, not the full reliability target or all scenarios. See [the readiness record](docs/submission-readiness.json) and [the saved report](traces/recorded/bad_deploy/report.json).

## Known limitations in this submission

- The broader reliability target and full agent-versus-baseline evaluation are incomplete.
- The historical pilot includes wrong diagnoses and provider-quota failures. It does not establish an accuracy advantage over the baseline.
- The newer causal-proof guard links the named culprit to inspected service-code evidence. It checks structural provenance, not whether a code line semantically explains every symptom.
- A fresh single-scenario smoke test, if successful, demonstrates that one path works. It does not establish multi-scenario accuracy or satisfy a three-out-of-five reliability target.
- Live investigations depend on free model availability. Recordings remain available without model requests.
- The application is a local, synthetic-data demonstrator, not a production incident-management service.

These are current limitations, not completed features relabelled as future scope.

## Future scope

- Production telemetry connectors such as Prometheus and Loki, instead of only the local capture pipeline.
- Multiple services and dependency-aware incident correlation.
- Authenticated production webhooks, role-based access and multiple human approvers.
- A larger runbook collection and semantic retrieval where keyword search becomes insufficient.
- Additional approved remediation actions and broader failure scenarios.
- Independent scenario variants and a larger paired evaluation of diagnosis accuracy, inconclusive reports, latency and quota use.

## Demo plan for submission

1. Introduce the problem and the limited MVP scope.
2. Show the checkout service, seeded failure and captured evidence.
3. Run the bad-deploy investigation if model access is available, or clearly select **Recorded replay**.
4. Explain the named culprit and its matching code citation.
5. Show the saved human approval and measured recovery from the historical real run. Do not describe a recording as a new execution.
6. Present the known limitations and future-scope list.

Do not execute a new remediation action without explicit human approval. The recorded fallback is sufficient to demonstrate the earlier verified approval flow transparently.

## Checks and supporting material

```bash
ONCALL_OFFLINE=1 .venv/bin/python -m pytest -q
.venv/bin/python scripts/rehearse.py
.venv/bin/python -m streamlit run ui/dashboard.py --server.address 127.0.0.1
```

See [demo instructions](docs/demo.md), [pilot results](docs/evaluation-results.md), [offline evidence audit](docs/offline-review.md), and [presentation notes](docs/presentation-notes.md).

## Suggested submission description

OnCall Agent is an MVP that investigates a checkout-service alert using read-only telemetry tools and runbook retrieval. It produces evidence-backed incident reports and requires human approval before remediation. The project includes a tested local service, a trace dashboard, real recorded investigations and a pilot evaluation. Broader reliability validation and production integrations remain future work.
