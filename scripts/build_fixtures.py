"""Produce one real, isolated evidence capture for each seeded failure."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def build():
    for scenario, failure, version in [("bad_deploy", "bad_deploy", "v1.1.0"),
                                        ("pool_exhaustion", "db_pool_exhaustion", "v1.2.0"),
                                        ("memory_leak", "memory_leak", "v1.3.0")]:
        destination = ROOT / "eval/fixtures" / scenario
        if destination.exists():
            print(f"Reusing {destination}", flush=True)
            continue
        with tempfile.TemporaryDirectory(prefix="oncall-fixture-") as directory:
            env = os.environ.copy()
            env.update(ONCALL_DATA=str(Path(directory) / "data"), ONCALL_SANDBOX=str(Path(directory) / "sandbox"))
            def run(*args):
                subprocess.run([sys.executable, *args], cwd=ROOT, env=env, check=True)
            try:
                run("scripts/devctl.py", "up", "--port", "18005")
                run("scripts/devctl.py", "inject", scenario)
                run("scripts/devctl.py", "check", "--seconds", "40" if scenario == "memory_leak" else "25")
                run("scripts/capture.py", str(destination))
                commits = json.loads((destination / "commits.json").read_text())
                decoy = version.removesuffix(".0") + ".1"
                answer = {"failure_type": failure, "accepted_culprits": [version, commits[version]["sha"]],
                          "decoys": [decoy, commits[decoy]["sha"]]}
                key = ROOT / "eval/keys" / f"{scenario}.json"
                key.parent.mkdir(parents=True, exist_ok=True)
                key.write_text(json.dumps(answer, indent=2) + "\n")
                print(f"Captured real evidence: {scenario}", flush=True)
            finally:
                run("scripts/devctl.py", "down")


if __name__ == "__main__":
    build()
