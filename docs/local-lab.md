# Local failure lab

Use the virtual environment from the repository root. No API keys are needed.

```bash
.venv/bin/python scripts/devctl.py up
.venv/bin/python scripts/devctl.py check --seconds 10
.venv/bin/python scripts/devctl.py inject bad_deploy
.venv/bin/python scripts/devctl.py check --seconds 15
.venv/bin/python scripts/devctl.py reset
.venv/bin/python scripts/devctl.py down
```

`up` builds `sandbox/checkout-service/` on first use, starts a supervisor and
service on `127.0.0.1:8001`, waits for health, then starts bounded concurrent
traffic at up to 15 requests/s. `--port` and `--cap-mb` can change the defaults.
An occupied port causes an error. Later commands remember the port and cap.

`inject` accepts `bad_deploy`, `pool_exhaustion`, or `memory_leak`. It deploys
the causal commit first and then a metadata-only decoy. Each actual deployment
is recorded. The latest deployment is deliberately not the root cause.
`reset` rolls back to the healthy tag and starts fresh processes; historical
logs and metrics remain available. `restart` keeps the currently deployed
version, so a code fault returns. `rollback v1.0.0` selects the healthy release.
These controls are operator commands; the future agent gets read-only tools
and must propose changes for human approval.

| Scenario | Causal release | Later decoy | Mechanism |
|---|---|---|---|
| Healthy | v1.0.0 | — | Normal checkout and history queries |
| Bad deploy | v1.1.0 | v1.1.1 | Missing currency context for a deterministic subset of customers |
| Pool exhaustion | v1.2.0 | v1.2.1 | Two connections, no overflow, 3 s query hold, 2 s pool timeout |
| Memory leak | v1.3.0 | v1.3.1 | Unbounded cache retains 2 MiB of touched random bytes per checkout |

The memory scenario starts returning HTTP 503 after retaining 96 MiB of
cache entries. The supervisor samples RSS every 0.2 s and kills the worker
when it exceeds 192 MiB, then starts it again. This is a simulated application
overload threshold and a supervisor-enforced kill, not a claim that macOS
generated an OOM event. Restarting delays the fault; rollback removes it.

Runtime evidence is stored in `data/`:

- `logs/service.jsonl`: real request logs with process-unique line IDs and release tags.
- `metrics.db`: `requests` (time, route, HTTP status, latency), `samples`
  (time, PID, RSS, release), and `events` (deploy/start/exit/memory cap events).
- `deploys.json`: actual deploy times, release tags, commit SHAs and messages.
- `worker.log`, `supervisor.log`, `loadgen.log`: process diagnostics.

Transport failures use status `0`; they are counted separately from HTTP 5xx.
Metrics may lag requests by about one second while the load generator batches
writes. Request metrics currently describe the generated traffic, not arbitrary
external clients. The supervisor owns RSS metrics. Database pool-use sampling
and snapshot capture belong to the telemetry milestone.

The load generator uses a fixed seed and bounded in-flight requests. The request
choices repeat; exact timings and error counts depend on scheduling. Separate
SQLite files hold checkout data and telemetry. Both use WAL mode.

Run the full real-process acceptance check (about two minutes):

```bash
.venv/bin/python scripts/scenario_check.py
```

It checks each fault exceeds 5% HTTP 5xx within 35 seconds, reset has less than
1% HTTP 5xx and no transport failures in an 8-second observation, and the
memory cap actually fires. It always stops the lab afterward. Stop an existing
lab before running it; use `--port 18002` if its default test port is occupied.
These short observations verify the mechanisms; frozen snapshots and the
later evaluation will provide repeatable diagnosis tests.

`ONCALL_DATA` and `ONCALL_SANDBOX` override runtime paths for isolated tests.
PID records include process creation times so stale IDs cannot target unrelated
processes. File locks prevent overlapping supervisors and operator commands.
Sandbox bootstrap refuses to overwrite a nonempty unrelated directory.
