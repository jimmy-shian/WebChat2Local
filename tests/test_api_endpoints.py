"""
FastAPI Endpoints Unit Test Suite.
Tests /v1/models, /v1/health, /v1/status, /v1/doctor, /v1/logs, and /v1/chat/completions.
"""

import sys
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.app import app
from server.bridge.ws_hub import hub, TurnEvent

client = TestClient(app)


def test_get_models_endpoint():
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    model_ids = [m["id"] for m in data["data"]]
    assert "gemini-web/pro" in model_ids
    assert "gemini-web/flash" in model_ids
    assert "gemini-web/flash-thinking" in model_ids


def test_get_health_endpoint():
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "browser_connected" in data
    assert "accepting_turns" in data


def test_get_status_endpoint():
    resp = client.get("/v1/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "browser_connected" in data
    assert "workspace" in data
    assert "doctor" in data


def test_get_doctor_endpoint():
    resp = client.get("/v1/doctor")
    assert resp.status_code == 200
    data = resp.json()
    assert "overall_status" in data
    assert "checks" in data


def test_get_logs_endpoint():
    resp = client.get("/v1/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data


def test_chat_completions_disconnected_error(monkeypatch):
    monkeypatch.setattr("server.app.direct_is_configured", lambda: False)
    payload = {
        "model": "gemini-web/pro",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
    }
    # When browser extension is disconnected and direct cookie is not configured, it should return HTTP 503
    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 503
    assert "extension is not connected" in resp.json()["detail"]


def test_chat_completions_prefers_direct_cookie_over_browser(monkeypatch):
    """A connected extension must not hijack cookie-only API requests."""
    calls = []

    async def fake_direct(prompt, model="gemini-web/pro"):
        calls.append("direct")
        yield TurnEvent(event_type="delta", text="direct answer", delta="direct answer")
        yield TurnEvent(event_type="done", text="direct answer")

    async def fake_browser(prompt, model="gemini-web/pro"):
        calls.append("browser")
        yield TurnEvent(event_type="done", text="browser answer")

    monkeypatch.setattr("server.app.direct_is_configured", lambda: True)
    monkeypatch.setattr("server.app.DIRECT_ONLY", True)
    monkeypatch.setattr("server.app.stream_generate", fake_direct)
    monkeypatch.setattr(type(hub), "is_connected", property(lambda self: True))
    monkeypatch.setattr(hub, "execute_turn", fake_browser)

    resp = client.post("/v1/chat/completions", json={
        "model": "gemini-web/pro",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
    })
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "direct answer"
    assert calls == ["direct"]


def test_dashboard_root():
    resp = client.get("/")
    assert resp.status_code == 200
