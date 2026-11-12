"""Structural provenance regression tests, independent of seeded answer labels."""
import json

from agent.causality import causal_errors, revision_facts, reference_in_text
from agent.schemas import Report
from agent.runner import investigate
from test_investigation import evidence, ScriptedProvider, valid_report


CODE = 'diff --git a/service/price.py b/service/price.py\n--- a/service/price.py\n+++ b/service/price.py\n@@ -1 +1 @@\n-    currency = "USD"\n+    currency = context["currency"]'
METADATA = 'diff --git a/release.json b/release.json\n--- a/release.json\n+++ b/release.json\n@@ -1 +1 @@\n-{"note":"old"}\n+{"note":"docs only"}'


def fact(tag="release-23", sha="a" * 40, diff=CODE):
    return revision_facts({"tag": tag, "sha": sha, "diff": diff})


def report(culprit="release-23"):
    data = valid_report()
    data["culprit"] = culprit
    return Report.model_validate(data)


def test_matching_inspected_code_and_citation_pass():
    assert causal_errors(report(), {"T3": fact()}) == []


def test_named_culprit_requires_inspection():
    assert causal_errors(report("uninspected-release"), {"T3": fact()})


def test_metadata_change_cannot_supply_code_proof():
    value = fact(diff=METADATA)
    assert value["changed_files"] == ["release.json"]
    assert not value["service_code_changed"]
    assert causal_errors(report(), {"T3": value})


def test_code_citation_from_another_commit_does_not_pass():
    assert causal_errors(report(), {"T4": fact(), "T3": fact("release-24", "b" * 40)})


def test_reference_boundaries_and_aliases():
    assert not reference_in_text("v1.1.0", "v1.1.01")
    assert not reference_in_text("v1.1.0", "v1.1.0.1")
    assert reference_in_text("release-23", "The culprit is release-23.")
    assert causal_errors(report("release-23 (" + "a" * 40 + ")"), {"T3": fact()}) == []
    assert causal_errors(report("release-23 and release-24"), {"T3": fact(), "T4": fact("release-24", "b" * 40)})


def test_removed_code_counts_but_comments_and_headers_do_not():
    removed = CODE.split('+    currency')[0]
    assert fact(diff=removed)["service_code_changed"]
    comment = CODE.split('@@')[0] + '@@ -1 +1 @@\n+# service/price.py changed in a comment'
    assert not fact(diff=comment)["service_code_changed"]


def test_metadata_report_gets_feedback_then_can_recover(evidence, tmp_path):
    path = evidence / "commits.json"
    commits = json.loads(path.read_text())
    commits["v1.1.1"] = {"sha": "def", "tag": "v1.1.1", "summary": "docs only", "diff": METADATA}
    path.write_text(json.dumps(commits))
    path = evidence / "deploys.json"
    deployments = json.loads(path.read_text())
    deployments.append({"ts": "2026-11-12T10:08:30Z", "version": "v1.1.1", "sha": "def", "summary": "docs only"})
    path.write_text(json.dumps(deployments))
    wrong = valid_report()
    wrong.update(culprit="v1.1.1", evidence=[{"tool_call_id": "T1", "quote": "missing currency"},
                                           {"tool_call_id": "T3", "quote": "docs only"}])
    corrected = valid_report()
    corrected["evidence"][1]["tool_call_id"] = "T4"
    provider = ScriptedProvider([
        ("update_plan", {"steps": ["Compare observed symptoms with code"], "reason": "Need causal proof"}),
        ("search_logs", {}), ("list_deploys", {}), ("git_show", {"revision": "v1.1.1"}),
        ("submit_report", wrong), ("git_show", {"revision": "v1.1.0"}), ("submit_report", corrected)])
    directory = investigate(evidence, tmp_path / "run", provider=provider)
    rows = [json.loads(x) for x in (directory / "trace.jsonl").read_text().splitlines()]
    assert any(r["kind"] == "validation_error" and "no service Python" in r["detail"] for r in rows)
    assert json.loads((directory / "report.json").read_text())["culprit"] == "v1.1.0"


def test_fixed_baseline_can_meet_same_code_proof_rule(evidence, tmp_path):
    path = evidence / "commits.json"
    commits = json.loads(path.read_text())
    commits["abc"] = commits["v1.1.0"]
    commits["def"] = {"sha": "def", "tag": "v1.1.1", "summary": "docs only", "diff": METADATA}
    path.write_text(json.dumps(commits))
    path = evidence / "deploys.json"
    deployments = json.loads(path.read_text())
    deployments.append({"ts": "2026-11-12T10:08:30Z", "version": "v1.1.1", "sha": "def", "summary": "docs only"})
    path.write_text(json.dumps(deployments))
    data = valid_report()
    data["evidence"][1]["tool_call_id"] = "T7"
    directory = investigate(evidence, tmp_path / "baseline", mode="baseline",
                            provider=ScriptedProvider([("submit_report", data)]))
    assert json.loads((directory / "run.json").read_text())["status"] == "completed"
    rows = [json.loads(line) for line in (directory / "trace.jsonl").read_text().splitlines()]
    assert [r["arguments"]["revision"] for r in rows if r["kind"] == "tool" and r["name"] == "git_show"] == ["def", "abc"]
