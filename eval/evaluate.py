"""Run equal-step/token-budget agent and fixed-pipeline evaluations on snapshots."""
import argparse
import csv
import json
import uuid
from pathlib import Path
from agent.runner import ROOT, investigate
from eval.grader import grade


def evaluate(model, runs=1, scenario=None, experiment="v6", retry_failed=False):
    results_dir = ROOT / "eval/results"
    results_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for key in sorted((ROOT / "eval/keys").glob("*.json")):
        answer = json.loads(key.read_text())
        if scenario and key.stem != scenario:
            continue
        for mode in ("agent", "baseline"):
            for seed in range(runs):
                identity = f"{experiment}-{key.stem}-{mode}-{model.replace('/', '-')}-{seed}"
                output = ROOT / "runs/eval" / identity
                if retry_failed and (output / "run.json").exists():
                    previous = json.loads((output / "run.json").read_text())
                    if previous["status"] in {"failed", "interrupted"}:
                        archive = ROOT / "runs/eval-archive" / (identity + "-" + uuid.uuid4().hex[:8])
                        archive.parent.mkdir(parents=True, exist_ok=True)
                        output.rename(archive)
                # Resume finished runs without making new quota requests; failures remain visible.
                if not (output / "run.json").exists():
                    investigate(ROOT / "eval/fixtures" / key.stem, output, model, mode, seed)
                meta = json.loads((output / "run.json").read_text())
                result = grade(output, answer)
                row = {"scenario": key.stem, "mode": mode, "seed": seed, "model": model,
                       **result, **{k: meta.get(k) for k in ("llm_calls", "cached_calls", "total_tokens", "provider_tokens", "duration_s")},
                       "run": str(output.relative_to(ROOT))}
                rows.append(row)
                print(json.dumps(row), flush=True)
    output = results_dir / f"{experiment}-{model.replace('/', '-')}.csv"
    if rows:
        with output.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--scenario")
    parser.add_argument("--experiment", default="v6")
    parser.add_argument("--retry-failed", action="store_true", help="Archive failed attempts and resume from cache; completed diagnoses are never rerun")
    args = parser.parse_args()
    if not 1 <= args.runs <= 5:
        parser.error("Use between 1 and 5 independent seeds")
    if not args.experiment.replace('-', '').isalnum():
        parser.error("experiment must be alphanumeric with optional hyphens")
    results = evaluate(args.model, args.runs, args.scenario, args.experiment, args.retry_failed)
    raise SystemExit(2 if any(row["status"] != "completed" for row in results) else 0)
