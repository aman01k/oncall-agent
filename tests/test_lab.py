"""Check failure mechanics without starting a server or using an LLM."""
import importlib.util
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lab
import bootstrap_sandbox as sandbox


def test_process_identity_rejects_reused_pid(tmp_path, monkeypatch):
    import json
    import os
    monkeypatch.setattr(lab, "DATA", tmp_path)
    (tmp_path / "worker.json").write_text(json.dumps({"pid": os.getpid(), "created": 0}))
    assert lab.managed("worker") is None


def test_sandbox_isolation_and_decoys(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "SANDBOX", tmp_path / "checkout-service")
    sandbox.bootstrap()
    for tag in sandbox.FAULT_TAGS.values():
        assert sandbox.git("diff", f"{tag}^", tag, "--", "service") == ""
        assert sandbox.git("diff", sandbox.HEALTHY, tag, "--", "service")
    sandbox.bootstrap()  # An existing lab is reused, never reset implicitly.
    assert sandbox.git("describe", "--tags", "--exact-match") == sandbox.HEALTHY


def test_bootstrap_refuses_nonempty_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "SANDBOX", tmp_path)
    (tmp_path / "user-file").write_text("keep")
    with pytest.raises(RuntimeError, match="overwrite"):
        sandbox.bootstrap()


def test_transport_errors_are_separate_from_5xx(tmp_path, monkeypatch):
    monkeypatch.setattr(lab, "DATA", tmp_path)
    with lab.metrics() as conn:
        conn.executemany("INSERT INTO requests VALUES (?, ?, ?, ?)",
                         [("2026", "/checkout", s, 1) for s in (200, 503, 0)])
    result = lab.request_summary("2025")
    assert result["http_5xx"] == 1
    assert result["network_errors"] == 1
    assert result["http_5xx_rate"] == pytest.approx(1 / 3)
