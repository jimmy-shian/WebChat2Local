import os
import pytest
from server.agent.permission_policy import ToolPermissionPolicy, PermissionLevel, AgentMode
from server.agent.context_manager import ContextBudgetManager
from server.agent.agent_orchestrator import AgentOrchestrator

def test_permission_policy():
    policy = ToolPermissionPolicy()
    
    # 1. Mode-based tool filtering
    ask_tools = policy.get_available_tools_for_mode(AgentMode.ASK)
    assert len(ask_tools) == 0
    
    agent_tools = policy.get_available_tools_for_mode(AgentMode.AGENT)
    assert "read_file" in agent_tools
    assert "run_command" in agent_tools
    
    # 2. Permission checks
    level, _ = policy.check_permission("read_file", {})
    assert level == PermissionLevel.AUTO
    
    level, _ = policy.check_permission("edit_file", {})
    assert level == PermissionLevel.CONFIRM
    
    # Autopilot
    policy.set_autopilot(True)
    level, _ = policy.check_permission("edit_file", {})
    assert level == PermissionLevel.AUTO
    policy.set_autopilot(False)
    
    # Safe commands
    level, _ = policy.check_permission("run_command", {"command": "pytest test.py"})
    assert level == PermissionLevel.SESSION_ALLOW
    
    # 3. Session allowance granting
    session_id = "test_session"
    policy.grant_session_allow(session_id, "delete_file")
    level, _ = policy.check_permission("delete_file", {}, session_id)
    assert level == PermissionLevel.SESSION_ALLOW

def test_context_manager(tmp_path):
    workspace = str(tmp_path)
    test_file = tmp_path / "test.py"
    test_file.write_text("print('hello')")
    
    manager = ContextBudgetManager(workspace_root=workspace)
    
    diff = manager.get_git_diff()
    assert isinstance(diff, str)
    
    prompt = "Please fix @test.py and also check @missing.py"
    refs = manager.resolve_file_references(prompt)
    assert len(refs) == 1
    assert refs[0]["path"] == "test.py"
    assert refs[0]["content"] == "print('hello')"
    
    ctx = manager.assemble_context(prompt=prompt)
    assert "files" in ctx
    assert len(ctx["files"]) == 1
    assert ctx["estimated_tokens"] > 0
    assert "repo_map" in ctx

@pytest.mark.asyncio
async def test_agent_orchestrator():
    orchestrator = AgentOrchestrator()
    
    session_id = orchestrator.create_session(AgentMode.AGENT)
    assert session_id in orchestrator.sessions
    
    events = []
    async for event in orchestrator.run_turn(session_id, "do something"):
        events.append(event)
        
    assert any(e["type"] == "edit.proposed" for e in events)
    
    proposal_id = list(orchestrator.sessions[session_id]["pending_proposals"].keys())[0] if orchestrator.sessions[session_id]["pending_proposals"] else None
    
    if proposal_id:
        res = orchestrator.accept_proposal(session_id, proposal_id)
        assert res["status"] == "accepted"
        assert proposal_id not in orchestrator.sessions[session_id]["pending_proposals"]
        
    orchestrator.cancel_session(session_id)
    assert orchestrator.sessions[session_id]["status"] == "cancelled"
    
    events_cancelled = []
    async for event in orchestrator.run_turn(session_id, "do something"):
        events_cancelled.append(event)
        
    assert events_cancelled[0]["summary"] == "Session cancelled"
