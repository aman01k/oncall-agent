"""Structural code provenance checks. No scenario labels or answer keys."""
from __future__ import annotations

import re
import shlex
import json

EVIDENCE_POLICY = "causal-v1"


def revision_facts(commit):
    """Extract changed service Python lines from a unified diff, not commit prose."""
    paths, lines = [], []
    current = None
    in_hunk = False
    for line in commit.get("diff", "").splitlines():
        if line.startswith("diff --git "):
            parts = shlex.split(line)
            current = parts[-1].removeprefix("b/") if len(parts) == 4 else None
            in_hunk = False
            if current and current not in paths:
                paths.append(current)
        elif line.startswith("@@"):
            in_hunk = True
        elif (in_hunk and current and current.startswith("service/") and current.endswith(".py")
              and line[:1] in {"+", "-"} and not line.startswith(("+++", "---"))):
            code = line[1:].strip()
            if code and not code.startswith("#"):
                lines.append(line)
    result = {"tag": commit.get("tag"), "sha": commit.get("sha"),
              "changed_files": paths[:8], "service_code_changed": bool(lines),
              "service_lines": [line[:240] for line in lines[:12]],
              "truncated": len(paths) > 8 or len(lines) > 12 or any(len(line) > 240 for line in lines)}
    while len(json.dumps(result)) > 1600:
        result["truncated"] = True
        if len(result["service_lines"]) > 1:
            result["service_lines"].pop()
        elif len(result["changed_files"]) > 1:
            result["changed_files"].pop()
        else:
            result["changed_files"] = [path[:240] for path in result["changed_files"]]
            break
    return result


def reference_in_text(reference, text):
    return bool(reference and re.search(r"(?<![\w./-])" + re.escape(reference) + r"(?![\w/-]|\.\w)", text))


def causal_errors(report, revisions):
    """Necessary code-proof conditions, not a semantic root-cause judge.

    revisions maps inspected tool IDs to facts from actual git_show outputs.
    The model must cite a changed service line from its own named culprit.
    """
    if report.failure_type == "unknown":
        return []
    matched = {call: facts for call, facts in revisions.items()
               if any(reference_in_text(facts.get(key), report.culprit) for key in ("tag", "sha"))}
    if not matched:
        return ["Inspect git_show for the exact release or full SHA named as culprit before submitting"]
    identities = {facts.get("sha") or facts.get("tag") for facts in matched.values()}
    if len(identities) != 1:
        return ["Name one causal revision; put other releases and ruled-out hypotheses in the summary"]
    code_calls = {call: facts for call, facts in matched.items() if facts["service_code_changed"]}
    if not code_calls:
        return ["Named culprit has no service Python code changes; inspect an earlier release rather than blaming metadata"]
    if not any(c.tool_call_id in code_calls and any(c.quote in line for line in code_calls[c.tool_call_id]["service_lines"])
               for c in report.evidence):
        return ["Cite an added or removed service-code line from the inspected revision named as culprit"]
    return []
