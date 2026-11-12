"""Offline checks do not instantiate a provider or perform remediation."""
import importlib.util
import json
from pathlib import Path

import pytest
from agent.runner import Provider
from agent.causality import EVIDENCE_POLICY
from test_investigation import valid_report


def test_offline_mode_refuses_provider_before_loading_key(monkeypatch):
    monkeypatch.setenv("ONCALL_OFFLINE", "1")
    with pytest.raises(RuntimeError, match="Offline mode"):
        Provider()


def test_new_policy_approval_revalidates_code_proof(tmp_path, monkeypatch):
    import actions.approval as approval
    monkeypatch.setattr(approval, "ROOT", tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.json").write_text(json.dumps({"status": "completed", "mode": "agent", "evidence_policy": EVIDENCE_POLICY}))
    (run / "report.json").write_text(json.dumps(valid_report()))
    (run / "trace.jsonl").write_text('')
    with pytest.raises(ValueError, match="Causal evidence check failed"):
        approval.decide(run, 0, True, "test approver")
    assert not (run / "decision-0.json").exists()


def test_historical_experiments_cannot_mix_new_policy(tmp_path, monkeypatch):
    from eval import evaluate
    monkeypatch.setattr(evaluate, "ROOT", tmp_path)
    keys = tmp_path / "eval/keys"
    keys.mkdir(parents=True)
    (keys / "case.json").write_text('{"failure_type":"bad_deploy"}')
    with pytest.raises(ValueError, match="frozen"):
        evaluate.evaluate("unused-model", experiment="v6", retry_failed=True)


def test_rehearsal_rejects_tampered_source_quote(tmp_path):
    import shutil
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("rehearse_module", root / "scripts/rehearse.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = tmp_path / "traces/recorded/tampered"
    shutil.copytree(root / "traces/recorded/bad_deploy", target)
    path = target / "report.json"
    report = json.loads(path.read_text())
    report["evidence"][0]["quote"] = "fabricated quote for rehearsal"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="Invalid recording"):
        module.rehearse(tmp_path)
