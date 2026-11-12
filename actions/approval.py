"""Human decisions and allowlisted remediation; model tools never import this."""
from __future__ import annotations
import fcntl
import json
import subprocess
import sys
import httpx
from pathlib import Path

from agent.runner import ROOT, emit, save_json, utc_now
from agent.schemas import Report
from agent.schemas import verify_evidence
from agent.causality import EVIDENCE_POLICY, causal_errors


def health():
    settings = json.loads((ROOT / "data/lab-settings.json").read_text())
    try:
        with httpx.Client(timeout=3, trust_env=False) as client:
            return all(client.get(f"http://127.0.0.1:{settings['port']}{path}").status_code == 200
                       for path in ("/health", "/health/db"))
    except httpx.RequestError:
        return False


def decide(run_directory, index, approve, actor):
    run_directory = Path(run_directory).resolve()
    if not actor.strip():
        raise ValueError("Human approver name is required")
    with (run_directory / "approval.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        metadata = json.loads((run_directory / "run.json").read_text())
        if metadata["status"] != "completed" or metadata["mode"] != "agent":
            raise ValueError("Only completed agent runs can propose remediation")
        report = Report.model_validate_json((run_directory / "report.json").read_text())
        if report.failure_type == "unknown":
            raise ValueError("Inconclusive reports cannot authorize remediation; investigate again")
        if not 0 <= index < len(report.proposed_actions):
            raise ValueError("Invalid proposed action")
        decision_file = run_directory / f"decision-{index}.json"
        if decision_file.exists():
            raise ValueError("This action already has a human decision")
        action = report.proposed_actions[index]
        if approve and metadata.get("evidence_policy") == EVIDENCE_POLICY:
            rows = [json.loads(line) for line in (run_directory / "trace.jsonl").read_text().splitlines()]
            outputs = {r["tool_call_id"]: r["result"] for r in rows if r["kind"] == "tool"}
            revisions = {r["tool_call_id"]: r["result"]["revision"] for r in rows
                         if r["kind"] == "tool" and r["name"] == "git_show" and "revision" in r["result"]}
            proof_errors = verify_evidence(report, outputs) + causal_errors(report, revisions)
            if proof_errors:
                raise ValueError("Causal evidence check failed: " + "; ".join(proof_errors))
        if action.kind == "rollback" and action.target != "v1.0.0":
            raise ValueError("Only the verified healthy release v1.0.0 is allowlisted")
        if action.kind == "restart" and action.target not in (None, ""):
            raise ValueError("Restart does not accept a target")
        # Stale snapshots and evaluation replays must never change the current lab.
        source = Path(metadata["source"])
        if not source.resolve().is_relative_to(ROOT / "data/snapshots"):
            raise ValueError("Only live incident captures can authorize remediation; evaluation and replay are read-only")
        snapshot_state = json.loads((source / "deployment-state.json").read_text())
        current_state = json.loads((ROOT / "data/deploys.json").read_text())[-1]
        if snapshot_state["id"] != current_state["id"] or snapshot_state["sha"] != current_state["sha"]:
            raise ValueError("Snapshot is from a different deployment; capture and investigate current evidence")
        decision = {"actor": actor.strip(), "at": utc_now(), "approved": bool(approve),
                    "action": action.model_dump(), "status": "approved" if approve else "rejected"}
        # Persist BEFORE running anything: repeated clicks must never execute twice.
        save_json(decision_file, decision)
        emit(run_directory, "approval", **decision)
        if not approve:
            return decision
        command = [sys.executable, str(ROOT / "scripts/devctl.py")]
        command += ["restart"] if action.kind == "restart" else ["rollback", action.target]
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
            check = subprocess.run([sys.executable, str(ROOT / "scripts/devctl.py"), "check", "--seconds", "10"],
                                   cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
            sample = json.loads(check.stdout)
            probes_ok = health()
            decision.update(status="executed", recovery=sample, health_ok=probes_ok,
                            recovered=bool(sample["requests"] >= 20 and sample["http_5xx_rate"] < .01
                                           and sample["network_errors"] == 0 and sample["supervisor_running"] and probes_ok))
        except (subprocess.SubprocessError, ValueError, OSError) as exc:
            decision.update(status="execution_failed", error=str(exc)[:300], recovered=False)
        save_json(decision_file, decision)
        emit(run_directory, "action_result", **decision)
        return decision
