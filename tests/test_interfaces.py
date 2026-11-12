"""Exercise the dashboard and webhook without consuming provider quota."""
from pathlib import Path
import threading
from fastapi.testclient import TestClient


def test_dashboard_renders():
    from streamlit.testing.v1 import AppTest
    page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/dashboard.py"))
    page.run(timeout=20)
    assert not page.exception
    assert page.title[0].value == "OnCall Agent"


def test_webhook_rejects_paths_and_bounds_queue(tmp_path, monkeypatch):
    import agent.api as api
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(api, "slot", threading.BoundedSemaphore(1))
    submitted = []
    monkeypatch.setattr(api.pool, "submit", lambda fn: submitted.append(fn))
    source = tmp_path / "eval/fixtures/test"
    source.mkdir(parents=True)
    (source / "alert.json").write_text('{}')
    client = TestClient(api.app)
    assert client.post('/alerts', json={"snapshot": "../../.env"}).status_code == 400
    assert client.post('/alerts', json={"snapshot": "eval/fixtures/test"}).status_code == 202
    assert client.post('/alerts', json={"snapshot": "eval/fixtures/test"}).status_code == 429
    assert len(submitted) == 1
