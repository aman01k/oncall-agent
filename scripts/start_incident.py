"""Threshold-checked live alert capture followed by a background investigation."""
import argparse
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from capture import capture
from agent.runner import investigate

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="openai/gpt-oss-20b")
    args = parser.parse_args()
    destination = ROOT / "data/snapshots" / uuid.uuid4().hex
    try:
        capture(destination)
        print(investigate(destination, model=args.model), flush=True)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Cannot start incident: {exc}\n")
