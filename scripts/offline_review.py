"""Audit historical reports with new provenance rules without rerunning a model."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["ONCALL_OFFLINE"] = "1"
from agent.causality import causal_errors, revision_facts
from agent.schemas import Report, verify_evidence


def audit(directory):
    directory = Path(directory)
    report = Report.model_validate_json((directory / "report.json").read_text())
    outputs, revisions = {}, {}
    for row in map(json.loads, (directory / "trace.jsonl").read_text().splitlines()):
        if row["kind"] != "tool":
            continue
        outputs[row["tool_call_id"]] = row["result"]
        if row["name"] == "git_show":
            result = row["result"]
            revisions[row["tool_call_id"]] = result.get("revision") or revision_facts(result)
    errors = verify_evidence(report, outputs) + causal_errors(report, revisions)
    return {"case": directory.name, "culprit": report.culprit, "passes_new_guard": not errors, "errors": errors}


def main():
    results = [audit(folder) for folder in sorted((ROOT / "eval/regressions").glob("*")) if folder.is_dir()]
    lines = ["# Offline failure analysis", "", "Historical model outputs, audited without API calls. Original v6 results remain unchanged.", "",
             "| Historical case | Named culprit | New guard | Reason |", "|---|---|---|---|"]
    for row in results:
        lines.append(f"| {row['case']} | {row['culprit']} | {'pass' if row['passes_new_guard'] else 'reject'} | "
                     + ("Inspected code and cited line match" if not row["errors"] else "; ".join(row["errors"])) + " |")
    lines += ["", "## What failed", "", "The two development-model decoy reports inspected the real code but named the later metadata-only deploy.",
              "Their excerpts were real. The old checks verified provenance but did not connect the named culprit to the inspected diff.", "",
              "The new guard requires one exact inspected tag/full SHA, a service Python change, and a changed-line citation from that same revision.",
              "It also rejects some historically correct diagnoses that lack the new proof. A rejection is not a claim that the old diagnosis was wrong.", "",
              "## Fairness and limitations", "", "The v7 baseline now inspects every returned recent deployed diff once using a fixed collection strategy.",
              "Both agent and baseline face the same stricter acceptance rule. v6 CSVs remain frozen and are not rescored as v7.",
              "This is an offline policy audit, not a new LLM benchmark. It proves neither better model accuracy nor that a selected code line logically explains the symptom.",
              "Fresh model evaluation, including independent scenario variants, remains pending free quota.", ""]
    (ROOT / "docs/offline-review.md").write_text("\n".join(lines))
    print(json.dumps({"mode": "offline", "audited_reports": len(results), "results": results}, indent=2))


if __name__ == "__main__":
    main()
