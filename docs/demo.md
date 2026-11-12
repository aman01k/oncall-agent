# OnCall Agent demo

From the repository root, activate `.venv` or prefix Python commands with
`.venv/bin/python`. Start the dashboard:

```bash
.venv/bin/python -m streamlit run ui/dashboard.py --server.address 127.0.0.1
```

1. Open the dashboard. Start the healthy lab if it is not already running.
2. Select `bad_deploy`, then inject it. The operator job box shows completion.
3. Wait about 45–90 seconds so failing traffic exceeds the generic alert threshold.
4. Select the development model (`gpt-oss-20b`) or the evaluated main model
   (`gpt-oss-120b`). Click **Capture alert and investigate** once.
5. Select the new incident and refresh progress. Show the public plan, the read-only
   tool calls, the metadata-only decoy diff and the earlier causal code change.
6. Show the report and exact evidence quotes. Explain that confidence is checked
   against distinct sources and the code diff, rather than treated as a probability.
7. Review the proposed rollback to `v1.0.0`. The human approver clicks **Approve
   and execute**. Show the decision record and measured recovery result.
8. Show the evaluation CSV and discuss both correct and failed runs. Then show
   a memory-leak recording to explain why a restart only delays that fault.

The agent has no executor tool. Only the separate approval code can call the
allowlisted operator commands. An old snapshot, evaluation fixture, duplicate
decision, invalid tag or missing human approver cannot execute remediation.
Replays have a visible banner and no approval buttons. A replay is a selected
successful recorded investigation, not a new live result or an accuracy estimate.

If the free provider rate-limits a run, the trace records the wait. Use the
**Recorded replay** tab while explaining that the API is unavailable. Do not
present a recording as live execution.

To verify locally:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/scenario_check.py
.venv/bin/python scripts/leak_check.py
```

The scenario check starts and stops the lab; stop the demo lab first. To stop
the service afterward, run `python scripts/devctl.py down`. Stop Streamlit with
Ctrl+C in the terminal running it.

Optional webhook (localhost only):

```bash
.venv/bin/python -m uvicorn agent.api:app --host 127.0.0.1 --port 8002
```

`POST /alerts` accepts `{"snapshot":"eval/fixtures/bad_deploy"}` and returns
a queued run ID. The endpoint permits only captured evidence folders and bounds
the background queue. It is a local classroom interface, not an authenticated
production integration.
