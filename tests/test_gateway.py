import pytest
from fastapi.testclient import TestClient
from core.audit import verify
import gateway.app as g


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(g, "MODE", "cleanroom")
    monkeypatch.setattr(g, "ADMIN_TOKEN", "t0k")
    monkeypatch.setattr(g, "call_model", lambda tenant, prompt: {"reply": "ok", "latency_ms": 20.0})
    g.chain.entries.clear()
    g.app.dependency_overrides[g.caller_ip] = lambda: "172.28.1.5"      # pretend we are red
    yield TestClient(g.app)
    g.app.dependency_overrides.clear()


def test_red_to_model_allowed(client):
    assert client.post("/send", json={"src": "red", "dst": "model", "message": "hi"}).status_code == 200


def test_red_to_blue_denied(client):
    assert client.post("/send", json={"src": "red", "dst": "blue", "message": "hi"}).status_code == 403


def test_impersonation_denied(client):
    assert client.post("/send", json={"src": "blue", "dst": "model", "message": "hi"}).status_code == 403


def test_log_has_hashes_not_text_and_verifies(client):
    client.post("/send", json={"src": "red", "dst": "model", "message": "CNRY-deadbeef secret words"})
    doc = client.get("/audit").json()
    assert "CNRY-deadbeef" not in str(doc) and verify(doc)[0] is True


def test_admin_needs_token(client):
    e = {"actor": "harness", "event": "finding", "data": "F1 VALID"}
    assert client.post("/admin/event", json=e).status_code == 401
    assert client.post("/admin/event", json=e, headers={"X-Admin-Token": "t0k"}).status_code == 200
