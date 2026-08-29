import pytest
from fastapi.testclient import TestClient
from server.server import app

client = TestClient(app)

def test_get_providers():
    response = client.get("/api/providers")
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert len(data["providers"]) > 0

def test_create_session():
    response = client.post("/api/sessions", json={"mode": "ASK"})
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["mode"] == "ASK"

def test_workspace_tree():
    response = client.get("/api/workspace/tree")
    assert response.status_code == 200
    data = response.json()
    # It might be empty or full, but it should be a JSON (dict)
    assert isinstance(data, dict)

def test_workspace_file():
    # Attempt to read a known file like README.md
    response = client.get("/api/workspace/file?path=README.md")
    assert response.status_code == 200
    data = response.json()
    assert "content" in data or "file_content" in data

def test_studio_html():
    response = client.get("/studio")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "WebChat2Local Studio" in response.text

def test_proposal_accept_reject():
    # create proposal
    response = client.post("/api/workspace/edit", json={"path": "test.txt", "content": "hello"})
    assert response.status_code == 200
    proposal_id = response.json()["proposal_id"]
    
    # accept
    res_accept = client.post(f"/api/proposals/{proposal_id}/accept")
    assert res_accept.status_code == 200
    assert res_accept.json()["status"] == "accepted"
    
    # reject
    res_reject = client.post(f"/api/proposals/{proposal_id}/reject")
    assert res_reject.status_code == 200
    assert res_reject.json()["status"] == "rejected"

def test_terminal_run():
    response = client.post("/api/terminal/run", json={"command": "echo hello", "timeout": 5})
    assert response.status_code == 200
    data = response.json()
    assert "exit_code" in data
    assert "stdout" in data
    assert "hello" in data["stdout"].lower()

def test_workspace_tree_path():
    response = client.get("/api/workspace/tree?path=server")
    assert response.status_code == 200
    data = response.json()
    assert "entries" in data
    assert data["path"] == "server"

def test_agent_chat():
    # First create a session
    sess_res = client.post("/api/sessions", json={"mode": "ASK"})
    session_id = sess_res.json()["session_id"]
    
    response = client.post("/api/agent/chat", json={
        "session_id": session_id,
        "prompt": "Hello",
    })
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    
    # Just read the response text
    content = response.text
    assert "event: message.chunk" in content
    assert "event: agent.completed" in content
