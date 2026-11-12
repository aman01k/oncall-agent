"""Copy validated successful evaluation runs into portable labelled demo replays."""
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.grader import grade
from agent.schemas import Report, verify_evidence


def record():
    saved = []
    for key in sorted((ROOT / "eval/keys").glob("*.json")):
        answer = json.loads(key.read_text())
        candidates = list((ROOT / "runs/eval").glob(f"*{key.stem}-agent-*/run.json"))
        candidates.sort(key=lambda p: (json.loads(p.read_text()).get("model") != "openai/gpt-oss-120b", str(p)))
        for metadata_path in candidates:
            source = metadata_path.parent
            if not grade(source, answer)["correct"]:
                continue
            target = ROOT / "traces/recorded" / key.stem
            target.mkdir(parents=True, exist_ok=True)
            for filename in ("run.json", "report.json"):
                value = json.loads((source / filename).read_text())
                if filename == "run.json":
                    value["source"] = str(Path(value["source"]).relative_to(ROOT))
                    value["replay"] = True
                (target / filename).write_text(json.dumps(value, indent=2) + "\n")
            rows = []
            for line in (source / "trace.jsonl").read_text().splitlines():
                value = json.loads(line)
                if "source" in value:
                    value["source"] = str(Path(value["source"]).relative_to(ROOT))
                rows.append(re.sub(r"org_[A-Za-z0-9_]+", "provider-organization", json.dumps(value)))
            (target / "trace.jsonl").write_text("\n".join(rows) + "\n")
            saved.append(key.stem)
            break
    print(json.dumps({"recorded_successful_runs": saved}))
    return saved


def record_live(source):
    source = Path(source).resolve()
    meta = json.loads((source / "run.json").read_text())
    decision = json.loads((source / "decision-0.json").read_text())
    report = Report.model_validate_json((source / "report.json").read_text())
    rows = [json.loads(line) for line in (source / "trace.jsonl").read_text().splitlines()]
    outputs = {row["tool_call_id"]: row["result"] for row in rows if row["kind"] == "tool"}
    if meta["status"] != "completed" or not decision.get("recovered") or verify_evidence(report, outputs):
        raise ValueError("Live replay requires a validated report and a measured, approved recovery")
    target = ROOT / "traces/recorded/live-approved-rollback"
    target.mkdir(parents=True, exist_ok=True)
    meta.update(source=str(Path(meta["source"]).relative_to(ROOT)), replay=True)
    for filename, value in [("run.json", meta), ("report.json", report.model_dump()), ("decision-0.json", decision)]:
        (target / filename).write_text(json.dumps(value, indent=2) + "\n")
    for row in rows:
        if "source" in row:
            row["source"] = str(Path(row["source"]).relative_to(ROOT))
    encoded = "\n".join(re.sub(r"org_[A-Za-z0-9_]+", "provider-organization", json.dumps(row)) for row in rows)
    (target / "trace.jsonl").write_text(encoded + "\n")
    print("Recorded approved live rollback", flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-run")
    args = parser.parse_args()
    record()
    if args.live_run:
        record_live(args.live_run)
