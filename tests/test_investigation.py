"""Behavioral tests for evidence boundaries, agent control and approval gates."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from agent.schemas import Report, verify_evidence
from agent.runner import investigate
from telemetry.tools import Tools


@pytest.fixture
def evidence(tmp_path):
    source = tmp_path / "snapshot"
    source.mkdir()
    values = {
        "alert": {"service": "checkout-api", "fired_at": "2026-11-12T10:10:00Z", "message": "5xx >5%"},
        "logs": [{"id": "L1", "ts": "2026-11-12T10:09:00Z", "level": "ERROR", "status": 500,
                  "route": "/checkout", "exc_type": "KeyError", "exc": "missing currency"},
                 {"id": "L2", "ts": "2026-11-12T11:00:00Z", "level": "ERROR", "status": 500, "route": "/later"}],
        "requests": [{"ts": "2026-11-12T10:09:00Z", "status": 500, "latency_ms": 2}],
        "samples": [{"ts": "2026-11-12T10:09:59Z", "rss_mb": 70}], "events": [],
        "deploys": [{"ts": "2026-11-12T10:08:00Z", "version": "v1.1.0", "sha": "abc", "summary": "currency context"}],
        "commits": {"v1.1.0": {"diff": "context[\"currency\"]", "sha": "abc"}},
        "health": {"status": "ok"},
        "deployment-state": {"id": "D1", "sha": "abc"},
    }
    for name, value in values.items():
        (source / (name + ".json")).write_text(json.dumps(value))
    return source


def valid_report():
    return {"summary": "Currency lookup failed after release", "failure_type": "bad_deploy", "culprit": "v1.1.0",
            "confidence": "medium", "timeline": [{"ts": "2026-11-12T10:09:00Z", "description": "First error"}],
            "evidence": [{"tool_call_id": "T1", "quote": "missing currency"},
                         {"tool_call_id": "T2", "quote": "currency context"}],
            "next_steps": ["Roll back and verify"],
            "proposed_actions": [{"kind": "rollback", "target": "v1.0.0", "reason": "Remove the pricing regression"}]}


def test_snapshot_clock_excludes_future_logs(evidence):
    result = Tools(evidence).search_logs()
    assert result["matching_errors"] == 1
    assert result["groups"][0]["samples"][0]["id"] == "L1"


def test_common_log_filter_syntax(evidence):
    tools = Tools(evidence)
    assert tools.search_logs("level:error status:5xx")["matching_errors"] == 1
    assert tools.search_logs("status:200")["matching_errors"] == 0


def test_tools_reject_traversal_and_arbitrary_calls(evidence):
    tools = Tools(evidence)
    with pytest.raises(ValueError):
        tools.read_runbook("../../.env")
    with pytest.raises(ValueError):
        tools.call("__getattribute__", {})
    with pytest.raises(ValueError):
        tools.git_show("HEAD; rm -rf something")


def test_undeployed_revision_is_not_exposed(evidence):
    path = evidence / "commits.json"
    commits = json.loads(path.read_text())
    commits["v9.0.0"] = {"diff": "unreleased code"}
    path.write_text(json.dumps(commits))
    with pytest.raises(ValueError):
        Tools(evidence).git_show("v9.0.0")


def test_fabricated_citation_rejected():
    report = Report.model_validate(valid_report())
    assert verify_evidence(report, {"T1": {"text": "missing currency"}, "T2": {"text": "currency context"}}) == []
    assert verify_evidence(report, {"T1": {"text": "something else"}})


class ScriptedProvider:
    def __init__(self, calls):
        self.calls = iter(calls)

    def call(self, messages, schemas, force_report=False):
        name, arguments = next(self.calls)
        return {"message": {"role": "assistant", "tool_calls": [{"id": str(len(messages)), "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)}}]},
                "usage": {"total_tokens": 20}}, False


def test_agent_runs_tools_and_validates_report(evidence, tmp_path):
    provider = ScriptedProvider([
        ("update_plan", {"steps": ["Check errors", "Compare deploy"], "reason": "Collect evidence"}),
        ("search_logs", {}), ("list_deploys", {}), ("submit_report", valid_report())])
    directory = investigate(evidence, tmp_path / "run", provider=provider)
    assert json.loads((directory / "run.json").read_text())["status"] == "completed"
    assert json.loads((directory / "report.json").read_text())["culprit"] == "v1.1.0"


def test_agent_retries_invented_quote(evidence, tmp_path):
    wrong = valid_report()
    wrong["evidence"][0]["quote"] = "invented log line"
    provider = ScriptedProvider([
        ("update_plan", {"steps": ["Check"], "reason": "Collect"}),
        ("search_logs", {}), ("list_deploys", {}),
        ("submit_report", wrong), ("submit_report", valid_report())])
    directory = investigate(evidence, tmp_path / "run", provider=provider)
    assert '"kind": "validation_error"' in (directory / "trace.jsonl").read_text()
    assert (directory / "report.json").exists()


def test_inconclusive_report_never_proposes_actions(evidence, tmp_path):
    report = valid_report()
    report.update(failure_type="unknown", confidence="high")
    provider = ScriptedProvider([
        ("update_plan", {"steps": ["Check"], "reason": "Collect"}),
        ("search_logs", {}), ("list_deploys", {}), ("submit_report", report)])
    directory = investigate(evidence, tmp_path / "run", provider=provider)
    result = json.loads((directory / "report.json").read_text())
    assert result["confidence"] == "low"
    assert result["proposed_actions"] == []


def test_model_selects_evidence_ids_and_app_copies_quotes(evidence, tmp_path):
    submission = valid_report()
    submission["evidence"] = [{"tool_call_id": "T1", "quote_id": "E1"},
                              {"tool_call_id": "T2", "quote_id": "E3"}]
    # IDs are generated from source string values, never from an answer key.
    provider = ScriptedProvider([
        ("update_plan", {"steps": ["Check"], "reason": "Collect"}),
        ("search_logs", {}), ("list_deploys", {}), ("submit_report", submission)])
    directory = investigate(evidence, tmp_path / "run", provider=provider)
    assert json.loads((directory / "run.json").read_text())["status"] == "completed"
    assert all("quote_id" not in c for c in json.loads((directory / "report.json").read_text())["evidence"])


def test_grader_distinguishes_correct_cause_from_decoy(evidence, tmp_path):
    from eval.grader import grade
    provider = ScriptedProvider([
        ("update_plan", {"steps": ["Check"], "reason": "Collect"}),
        ("search_logs", {}), ("list_deploys", {}), ("submit_report", valid_report())])
    directory = investigate(evidence, tmp_path / "run", provider=provider)
    answer = {"failure_type": "bad_deploy", "accepted_culprits": ["v1.1.0"], "decoys": ["v1.1.1"]}
    assert grade(directory, answer)["correct"]
    report = json.loads((directory / "report.json").read_text())
    report["culprit"] = "v1.1.1"
    (directory / "report.json").write_text(json.dumps(report))
    result = grade(directory, answer)
    assert result["evidence_valid"] and result["decoy_blamed"] and not result["correct"]


def test_approval_gate_rejects_stale_and_duplicate_decisions(tmp_path, monkeypatch):
    import actions.approval as approval
    monkeypatch.setattr(approval, "ROOT", tmp_path)
    source = tmp_path / "data/snapshots/live"
    source.mkdir(parents=True)
    (source / "deployment-state.json").write_text(json.dumps({"id": "D1", "sha": "abc"}))
    (tmp_path / "data/deploys.json").write_text(json.dumps([{"id": "D2", "sha": "xyz"}]))
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.json").write_text(json.dumps({"status": "completed", "mode": "agent", "source": str(source)}))
    (run / "report.json").write_text(json.dumps(valid_report()))
    with pytest.raises(ValueError, match="different deployment"):
        approval.decide(run, 0, True, "test-human")
    (tmp_path / "data/deploys.json").write_text(json.dumps([{"id": "D1", "sha": "abc"}]))
    decision = approval.decide(run, 0, False, "test-human")
    assert decision["status"] == "rejected"
    with pytest.raises(ValueError, match="already"):
        approval.decide(run, 0, True, "test-human")


def test_approval_only_executes_allowlisted_command_after_approval(tmp_path, monkeypatch):
    import actions.approval as approval
    monkeypatch.setattr(approval, "ROOT", tmp_path)
    source = tmp_path / "data/snapshots/live"
    source.mkdir(parents=True)
    state = {"id": "D1", "sha": "abc"}
    (source / "deployment-state.json").write_text(json.dumps(state))
    (tmp_path / "data/deploys.json").write_text(json.dumps([state]))
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.json").write_text(json.dumps({"status": "completed", "mode": "agent", "source": str(source)}))
    (run / "report.json").write_text(json.dumps(valid_report()))
    commands = []
    def execute(command, **kwargs):
        commands.append(command)
        assert (run / "decision-0.json").exists()
        return SimpleNamespace(stdout=json.dumps({"requests": 100, "http_5xx_rate": 0,
                               "network_errors": 0, "supervisor_running": True}))
    monkeypatch.setattr(approval.subprocess, "run", execute)
    monkeypatch.setattr(approval, "health", lambda: True)
    result = approval.decide(run, 0, True, "test-human")
    assert result["recovered"]
    assert commands[0][-2:] == ["rollback", "v1.0.0"]
