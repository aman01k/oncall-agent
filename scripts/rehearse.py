"""Rehearse saved incident evidence and approved recovery with no API or system changes."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["ONCALL_OFFLINE"] = "1"
from agent.schemas import Report, verify_evidence


def rehearse(root=ROOT):
    recordings = sorted((root / "traces/recorded").glob("*/run.json"))
    if not recordings:
        raise ValueError("No real recordings available")
    checked = []
    for metadata_path in recordings:
        folder = metadata_path.parent
        metadata = json.loads(metadata_path.read_text())
        report = Report.model_validate_json((folder / "report.json").read_text())
        rows = [json.loads(line) for line in (folder / "trace.jsonl").read_text().splitlines()]
        outputs = {r["tool_call_id"]: r["result"] for r in rows if r["kind"] == "tool"}
        if metadata["status"] != "completed" or not metadata.get("replay") or verify_evidence(report, outputs):
            raise ValueError(f"Invalid recording: {folder.name}")
        item = {"recording": folder.name, "model": metadata["model"], "recorded_at": metadata["started_at"],
                "tool_calls": len(outputs), "evidence_verified": True}
        decision_path = folder / "decision-0.json"
        if decision_path.exists():
            decision = json.loads(decision_path.read_text())
            sample = decision.get("recovery", {})
            if not (decision.get("approved") and decision.get("recovered") and decision.get("health_ok")
                    and sample.get("requests", 0) >= 20 and sample.get("http_5xx") == 0 and sample.get("network_errors") == 0):
                raise ValueError("Recorded recovery does not meet the demonstrated outcome")
            item["approved_recovery"] = sample
        checked.append(item)
    return checked


if __name__ == "__main__":
    print(json.dumps({"mode": "REPLAY ONLY", "system_changes": False, "model_requests": 0,
                      "recordings": rehearse()}, indent=2))
