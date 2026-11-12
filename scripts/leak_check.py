"""Audit evidence folders for accidental answers or secrets before publication."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"alert.json", "logs.json", "requests.json", "samples.json", "events.json", "deploys.json",
           "deployment-state.json", "commits.json", "health.json"}


def audit(folder):
    errors = []
    for path in Path(folder).iterdir():
        if path.name not in ALLOWED:
            errors.append(f"Unexpected evidence file: {path.name}")
            continue
        raw = path.read_text()
        if re.search(r"gsk_[A-Za-z0-9]{15,}|AIza[A-Za-z0-9_-]{20,}|github_pat_", raw):
            errors.append(f"Possible credential in {path.name}")
        value = json.loads(raw)
        if path.name == "alert.json" and any(key in value for key in ("failure_type", "culprit", "scenario")):
            errors.append("Alert contains answer fields")
        if path.name in {"logs.json", "events.json"} and any(
            key in raw for key in ('"expected_culprit"', '"answer_key"', '"fault_switch"')):
            errors.append(f"Answer metadata in {path.name}")
    return errors


if __name__ == "__main__":
    issues = {p.name: audit(p) for p in (ROOT / "eval/fixtures").iterdir() if p.is_dir()}
    print(json.dumps(issues, indent=2))
    raise SystemExit(int(any(issues.values())))
