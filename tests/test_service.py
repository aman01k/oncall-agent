"""Basic tests for checkout-api. Each test gets its own database and log file."""

from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "service.jsonl"))
    import service.app as app_module

    app_module = importlib.reload(app_module)
    with TestClient(app_module.app) as c:
        c.log_file = tmp_path / "service.jsonl"
        yield c


def read_log(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_db(client):
    r = client.get("/health/db")
    assert r.status_code == 200


def test_checkout_and_history(client):
    r = client.post("/checkout", json={
        "customer_id": "c-1", "items": [{"sku": "SKU-1001", "qty": 2}, {"sku": "SKU-1003", "qty": 1}],
    })
    assert r.status_code == 200
    assert r.json()["total"] == 46.0

    h = client.get("/orders/history", params={"customer_id": "c-1"})
    assert h.status_code == 200
    assert len(h.json()["orders"]) == 1


def test_unknown_sku_is_400(client):
    r = client.post("/checkout", json={"customer_id": "c-1", "items": [{"sku": "NOPE", "qty": 1}]})
    assert r.status_code == 400


def test_every_request_is_logged_as_json(client):
    client.get("/health")
    r = client.get("/orders/history", params={"customer_id": "c-2"})
    request_id = r.headers["x-request-id"]
    lines = read_log(client.log_file)
    requests = [line for line in lines if line.get("event") == "request"]
    assert len(requests) == 2
    line = next(x for x in requests if x["request_id"] == request_id)
    assert line["route"] == "/orders/history"
    assert line["status"] == 200
    assert line["ts"].endswith("Z")
    assert line["id"].startswith("L")
