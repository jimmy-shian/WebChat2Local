"""
End-to-end synthetic turn execution test simulating WebSocket extension protocol.
"""

import sys
import asyncio
import json
import pytest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.bridge.ws_hub import hub, BrowserWebSocketHub


class MockWebSocket:
    def __init__(self):
        self.sent_messages = []

    async def accept(self):
        pass

    async def send_text(self, text: str):
        self.sent_messages.append(text)


@pytest.mark.asyncio
async def test_end_to_end_synthetic_turn():
    test_hub = BrowserWebSocketHub()
    mock_ws = MockWebSocket()

    # 1. Register mock connection
    await test_hub.register_connection(mock_ws)
    assert test_hub.is_connected is True

    # Send ready status
    await test_hub.handle_incoming_message({
        "type": "ready",
        "meta": {"url": "https://gemini.google.com/app", "model": "Google Gemini 2.5 Pro"}
    })
    assert test_hub.browser_info["model_name"] == "Google Gemini 2.5 Pro"

    # 2. Start turn in background
    async def run_turn():
        events = []
        async for ev in test_hub.execute_turn(prompt="What is 2+2?", model="gemini-web/pro", timeout_sec=5):
            events.append(ev)
        return events

    turn_task = asyncio.create_task(run_turn())
    await asyncio.sleep(0.05)

    # 3. Verify outgoing prompt submission
    assert len(mock_ws.sent_messages) > 0
    outgoing_msg = json.loads(mock_ws.sent_messages[-1])
    assert outgoing_msg["type"] == "submit_prompt"
    turn_id = outgoing_msg["turn_id"]
    assert "What is 2+2?" in outgoing_msg["prompt"]

    # 4. Simulate streamed chunks from extension
    await test_hub.handle_incoming_message({
        "type": "chunk",
        "turn_id": turn_id,
        "text": "",
        "delta": "",
        "thought": "Calculating addition",
        "thought_delta": "Calculating addition"
    })

    await test_hub.handle_incoming_message({
        "type": "chunk",
        "turn_id": turn_id,
        "text": "2 + 2 = 4",
        "delta": "2 + 2 = 4",
        "thought": "Calculating addition",
        "thought_delta": ""
    })

    # 5. Simulate done
    await test_hub.handle_incoming_message({
        "type": "done",
        "turn_id": turn_id,
        "text": "2 + 2 = 4",
        "thought": "Calculating addition"
    })

    # 6. Verify result
    events = await turn_task
    assert len(events) >= 2
    assert events[0].thought == "Calculating addition"
    assert events[-1].type == "done"
    assert events[-1].text == "2 + 2 = 4"
