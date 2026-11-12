"""Exercise each real fault and recovery with a running service (about 2 min)."""
from __future__ import annotations

import json

from bootstrap_sandbox import FAULT_TAGS, git
from devctl import check, deploy, down, inject, up
from lab import DATA, metrics, now


def run(port):
    results = []
    try:
        up(port=port)
        for scenario, tag in FAULT_TAGS.items():
            started_at = now()
            inject(scenario)
            # Include several allocation/kill cycles in the memory scenario.
            fault = check(35 if scenario == "memory_leak" else 15)
            assert fault["requests"] >= 20, fault
            assert fault["http_5xx_rate"] > 0.05, fault
            print(json.dumps({"scenario": scenario, "fault": fault}), flush=True)
            if scenario == "memory_leak":
                with metrics() as conn:
                    count = conn.execute("SELECT COUNT(*) FROM events WHERE kind='memory_limit_exceeded' AND ts>=?",
                                         (started_at,)).fetchone()[0]
                assert count > 0, "Memory cap was never exercised"
            # Rolling back the decoy must leave the causal code unchanged.
            assert git("diff", f"{tag}^", tag, "--", "service") == ""
            deploy("v1.0.0")
            recovery = check(8)
            assert recovery["requests"] >= 20, recovery
            assert recovery["http_5xx_rate"] < 0.01, recovery
            assert recovery["network_errors"] == 0, recovery
            print(json.dumps({"scenario": scenario, "recovery": recovery}), flush=True)
            results.append({"scenario": scenario, "fault": fault, "recovery": recovery})
        return results
    finally:
        down()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18001)
    args = parser.parse_args()
    result = {"results": run(args.port)}
    (DATA / "scenario_check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
