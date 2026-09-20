import base64
import json
import pytest
from fastapi.testclient import TestClient

from server.app import app
from server.protocol import ChatMessage, ToolCall, FunctionCall, extract_images_from_messages
from server.bridge.session_manager import SessionManager
from server.bridge.ws_hub import TurnEvent

client = TestClient(app)


def test_multiturn_session_fingerprint_continuity():
    msgs1 = [
        ChatMessage(role="system", content="You are Cline, a coding assistant."),
        ChatMessage(role="user", content="Inspect package.json and add a build script."),
    ]
    fp1 = SessionManager.get_conversation_fingerprint(msgs1)

    msgs2 = msgs1 + [
        ChatMessage(
            role="assistant",
            tool_calls=[ToolCall(id="call_1", function=FunctionCall(name="read_file", arguments='{"path":"package.json"}'))],
        ),
        ChatMessage(
            role="tool",
            tool_call_id="call_1",
            name="read_file",
            content='{"name": "my-app", "version": "1.0.0"}',
        ),
    ]
    fp2 = SessionManager.get_conversation_fingerprint(msgs2)

    msgs3 = msgs2 + [
        ChatMessage(
            role="assistant",
            tool_calls=[ToolCall(id="call_2", function=FunctionCall(name="write_to_file", arguments='{"path":"package.json","content":"..."}'))],
        ),
        ChatMessage(
            role="tool",
            tool_call_id="call_2",
            name="write_to_file",
            content="File written successfully",
        ),
    ]
    fp3 = SessionManager.get_conversation_fingerprint(msgs3)

    assert fp1 == fp2 == fp3, f"Fingerprints diverged across turns: {fp1} != {fp2} != {fp3}"


def test_incremental_prompt_compilation_for_continuation():
    msgs1 = [
        ChatMessage(role="system", content="System directive"),
        ChatMessage(role="user", content="First task prompt"),
    ]
    p1 = SessionManager.compile_rich_prompt(msgs1, for_stateful_session=True)
    assert "First task prompt" in p1.text
    assert "System directive" in p1.text
    assert "<system_instructions>" not in p1.text

    msgs2 = msgs1 + [
        ChatMessage(
            role="assistant",
            content="I will read the file.",
            tool_calls=[ToolCall(id="call_1", function=FunctionCall(name="read_file", arguments='{"path":"package.json"}'))],
        ),
        ChatMessage(
            role="tool",
            tool_call_id="call_1",
            name="read_file",
            content='{"scripts": {"test": "echo test"}}',
        ),
    ]
    p2 = SessionManager.compile_rich_prompt(msgs2, for_stateful_session=True)
    assert "Tool result" in p2.text
    assert "read_file" in p2.text
    assert '{"scripts": {"test": "echo test"}}' in p2.text
    assert "First task prompt" not in p2.text
    assert "<system_instructions>" not in p2.text
    assert "<tool_result" not in p2.text
    assert "<user>" not in p2.text
    assert len(p2.text) < 1000



def test_multimodal_image_extraction():
    img_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b64_data = base64.b64encode(img_bytes).decode("ascii")
    msg = ChatMessage(
        role="user",
        content=[
            {"type": "text", "text": "What is in this screenshot?"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_data}"}},
        ],
    )
    files = extract_images_from_messages([msg])
    assert len(files) == 1
    assert files[0].name.endswith(".png")
    assert files[0].getvalue() == img_bytes


def test_cookie_hot_reload_endpoint(monkeypatch):
    import uuid
    reloaded = []

    async def fake_reload():
        reloaded.append(True)

    monkeypatch.setattr("server.browser.gemini_direct.reload_client", fake_reload)
    
    unique_psid = f"test_psid_{uuid.uuid4().hex}"
    unique_psidts = f"test_psidts_{uuid.uuid4().hex}"

    # Test 1: New cookies trigger reload
    resp1 = client.post(
        "/v1/cookies",
        json={"1psid": unique_psid, "1psidts": unique_psidts, "source": "test"},
    )
    assert resp1.status_code == 200
    assert len(reloaded) == 1

    # Test 2: Identical cookies do NOT trigger reload (prevents dropping active streams)
    resp2 = client.post(
        "/v1/cookies",
        json={"1psid": unique_psid, "1psidts": unique_psidts, "source": "test"},
    )
    assert resp2.status_code == 200
    assert resp2.json().get("message") == "Cookies unchanged"
    assert len(reloaded) == 1




def test_end_to_end_agent_workflow_simulation(monkeypatch):
    dispatched_turns = []

    def mock_resolve_turn(prompt, model, is_new_session=True, session_id=None, is_continuation=False, files=None):
        dispatched_turns.append({
            "prompt": prompt,
            "model": model,
            "is_new_session": is_new_session,
            "session_id": session_id,
            "is_continuation": is_continuation,
            "files_count": len(files) if files else 0,
        })
        async def mock_stream():
            if not is_continuation:
                yield TurnEvent(
                    event_type="delta",
                    text='<tool_call>{"name": "read_file", "arguments": {"path": "config.json"}}</tool_call>',
                    delta='<tool_call>{"name": "read_file", "arguments": {"path": "config.json"}}</tool_call>',
                )
                yield TurnEvent(
                    event_type="done",
                    text='<tool_call>{"name": "read_file", "arguments": {"path": "config.json"}}</tool_call>',
                )
            else:
                yield TurnEvent(
                    event_type="delta",
                    text="Successfully read config.json. The app is ready.",
                    delta="Successfully read config.json. The app is ready.",
                )
                yield TurnEvent(
                    event_type="done",
                    text="Successfully read config.json. The app is ready.",
                )
        return mock_stream(), "direct"

    monkeypatch.setattr("server.app.resolve_turn", mock_resolve_turn)

    tools_def = [{
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file from disk",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
        },
    }]

    resp1 = client.post("/v1/chat/completions", json={
        "model": "gemini-web/pro",
        "messages": [
            {"role": "system", "content": "You are Cline."},
            {"role": "user", "content": "Read config.json please."},
        ],
        "tools": tools_def,
        "stream": False,
    })
    assert resp1.status_code == 200
    data1 = resp1.json()
    choice1 = data1["choices"][0]
    assert choice1["finish_reason"] == "tool_calls"
    assert len(choice1["message"]["tool_calls"]) == 1
    assert choice1["message"]["tool_calls"][0]["function"]["name"] == "read_file"

    assert len(dispatched_turns) == 1
    assert dispatched_turns[0]["is_continuation"] is False
    assert dispatched_turns[0]["is_new_session"] is True
    sid1 = dispatched_turns[0]["session_id"]

    resp2 = client.post("/v1/chat/completions", json={
        "model": "gemini-web/pro",
        "messages": [
            {"role": "system", "content": "You are Cline."},
            {"role": "user", "content": "Read config.json please."},
            {"role": "assistant", "tool_calls": choice1["message"]["tool_calls"]},
            {"role": "tool", "tool_call_id": choice1["message"]["tool_calls"][0]["id"], "name": "read_file", "content": '{"port": 8080}'},
        ],
        "tools": tools_def,
        "stream": False,
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    choice2 = data2["choices"][0]
    assert choice2["finish_reason"] == "stop"
    assert "Successfully read config.json" in choice2["message"]["content"]

    assert len(dispatched_turns) == 2
    assert dispatched_turns[1]["is_continuation"] is True
    assert dispatched_turns[1]["is_new_session"] is False
    assert dispatched_turns[1]["session_id"] == sid1
    assert "Tool result" in dispatched_turns[1]["prompt"]
    assert "<tool_result" not in dispatched_turns[1]["prompt"]
    assert '{"port": 8080}' in dispatched_turns[1]["prompt"]
