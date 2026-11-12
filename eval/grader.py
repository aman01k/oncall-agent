"""Deterministic grading; answer labels are never exposed to the agent."""
import json
from pathlib import Path
from agent.schemas import Report, verify_evidence
from agent.causality import EVIDENCE_POLICY, causal_errors, revision_facts


def grade(run_directory, answer):
    path = Path(run_directory)
    meta = json.loads((path / "run.json").read_text())
    report_path = path / "report.json"
    result = {"status": meta["status"], "correct": False, "evidence_valid": False,
              "decoy_blamed": False, "failure_type_correct": False, "culprit_correct": False,
              "confidence": None, "causal_proof_valid": False}
    if not report_path.exists():
        return result
    report = Report.model_validate_json(report_path.read_text())
    outputs, revisions = {}, {}
    for line in (path / "trace.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row["kind"] == "tool":
            outputs[row["tool_call_id"]] = row["result"]
            if row["name"] == "git_show":
                value = row["result"]
                revisions[row["tool_call_id"]] = value.get("revision") or revision_facts(value)
    result.update(failure_type_correct=report.failure_type == answer["failure_type"],
                  culprit_correct=any(ref in report.culprit for ref in answer["accepted_culprits"]),
                  decoy_blamed=any(ref in report.culprit for ref in answer["decoys"]),
                  evidence_valid=not verify_evidence(report, outputs), confidence=report.confidence,
                  causal_proof_valid=not causal_errors(report, revisions) and report.failure_type != "unknown")
    result["correct"] = bool(result["failure_type_correct"] and result["culprit_correct"]
                             and result["evidence_valid"] and not result["decoy_blamed"])
    if meta.get("evidence_policy") == EVIDENCE_POLICY:
        result["correct"] = result["correct"] and result["causal_proof_valid"] and meta["status"] == "completed"
    return result
