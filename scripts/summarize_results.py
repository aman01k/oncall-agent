"""Publish a transparent pilot summary, separating quota failures from diagnoses."""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def summarize():
    grouped = defaultdict(list)
    for csv_path in sorted((ROOT / "eval/results").glob("v6-*.csv")):
        with csv_path.open() as file:
            for row in csv.DictReader(file):
                grouped[(row["model"], row["mode"])].append(row)
    lines = ["# Pilot evaluation results", "", "Experiment: **v6**. Real captured evidence; no simulated LLM responses.", "",
             "| Model | Method | Attempts | Completed reports | Correct | Wrong completed | Quota-limited |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for (model, mode), rows in sorted(grouped.items()):
        completed = sum(r["status"] == "completed" for r in rows)
        correct = sum(r["correct"] == "True" for r in rows)
        quota = unknown_quota = 0
        for row in rows:
            metadata_path = ROOT / row["run"] / "run.json"
            if metadata_path.exists():
                meta = json.loads(metadata_path.read_text())
                quota += int("quota" in meta.get("error", "").lower())
            elif row["status"] != "completed":
                unknown_quota += 1
        lines.append(f"| {model} | {mode} | {len(rows)} | {completed} | {correct} | {completed-correct} | {str(quota) if not unknown_quota else str(quota) + " known; " + str(unknown_quota) + " unknown"} |")
    lines += ["", "The main-model batch covers all three faults once. The development-model batch covers five bad-deploy seeds.",
              "These are different task sets; do not compare their totals as equivalent benchmarks.", "",
              "Quota-limited attempts are retained in the CSV as failures to complete, but are not called wrong diagnoses.",
              "A completed report can still be incorrect (wrong type, wrong culprit or decoy blamed).", "",
              "In the main-model bad-deploy trial, both methods correctly identified the cause. That trial does not show an accuracy advantage for the agent.",
              "The incomplete batches cannot support a general accuracy or superiority claim.", "",
              "Earlier development experiments remain in separate CSVs. They used evolving report protocols and are not pooled into v6.", "",
              "## Start the new protocol after free quota replenishes", "", "```bash",
              "python -m eval.evaluate --model openai/gpt-oss-120b --runs 1 --experiment v7",
              "python -m eval.evaluate --model openai/gpt-oss-20b --scenario bad_deploy --runs 5 --experiment v7",
              "```", "", "v6 is frozen. v7 uses stricter causal proof and a stronger fixed collector, so its outcomes must remain separate.",
              "Use --retry-failed only within a compatible v7 experiment; never reinterpret v6 results as v7.", ""]
    (ROOT / "docs/evaluation-results.md").write_text("\n".join(lines))


if __name__ == "__main__":
    summarize()
