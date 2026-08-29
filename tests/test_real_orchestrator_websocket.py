import pytest
import asyncio
import json
from server.agent.agent_orchestrator import AgentOrchestrator
from server.core.constants import EventType

@pytest.mark.asyncio
async def test_full_orchestrator_real_websocket_turn():
    """Simulates real WebSocket incoming messages from the browser extension and validates tool execution."""
    
    # 1. Mock dispatch_fn returning a queue simulating real extension output
    async def mock_dispatch_fn(job_data):
        q = asyncio.Queue()
        # Extension sends chunk
        await q.put({
            "type": "chunk",
            "request_id": job_data["request_id"],
            "delta": '{"tool":"create_file","arguments":{"path":"RealNew.txt","content":"Hello from Real Test"}}',
            "accumulated": '{"tool":"create_file","arguments":{"path":"RealNew.txt","content":"Hello from Real Test"}}'
        })
        # Extension sends done
        await q.put({
            "type": "done",
            "request_id": job_data["request_id"],
            "full_text": '{"tool":"create_file","arguments":{"path":"RealNew.txt","content":"Hello from Real Test"}}',
            "finish_reason": "stop"
        })
        return q

    orchestrator = AgentOrchestrator(dispatch_fn=mock_dispatch_fn)
    orchestrator.policy.set_autopilot(True)
    session_id = orchestrator.create_session()
    
    events = []
    async for event in orchestrator.run_turn(session_id, '新增一個"RealNew.txt"，內容寫"Hello from Real Test"'):
        events.append(event)

    event_types = [e["type"] for e in events]
    assert EventType.MESSAGE_CHUNK.value in event_types
    assert EventType.TOOL_EXECUTED.value in event_types
    assert EventType.AGENT_COMPLETED.value in event_types

    # Find the tool executed event
    tool_exec_event = next(e for e in events if e["type"] == EventType.TOOL_EXECUTED.value)
    assert tool_exec_event["tool"] == "create_file"
    assert tool_exec_event["arguments"]["path"] == "RealNew.txt"
    assert tool_exec_event["result"]["success"] is True

    # Verify file is on disk
    import os
    target_file = os.path.join(orchestrator.workspace_root, "RealNew.txt")
    assert os.path.exists(target_file)
    with open(target_file, "r", encoding="utf-8") as f:
        assert f.read() == "Hello from Real Test"

    # Cleanup
    os.remove(target_file)
