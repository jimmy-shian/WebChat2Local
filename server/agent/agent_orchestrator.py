import uuid
from typing import AsyncGenerator, Dict, Any, Optional
from .permission_policy import AgentMode, ToolPermissionPolicy, PermissionLevel

class AgentOrchestrator:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.policy = ToolPermissionPolicy()
        
    def create_session(self, mode: AgentMode = AgentMode.AGENT) -> str:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "mode": mode,
            "history": [],
            "pending_proposals": {},
            "status": "active"
        }
        return session_id
        
    def cancel_session(self, session_id: str):
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = "cancelled"
            
    async def run_turn(self, session_id: str, prompt: str, active_file: str = None, model: str = "auto") -> AsyncGenerator[dict, None]:
        if session_id not in self.sessions:
            yield {"type": "agent.completed", "summary": "Session not found"}
            return
            
        session = self.sessions[session_id]
        if session["status"] == "cancelled":
            yield {"type": "agent.completed", "summary": "Session cancelled"}
            return
            
        yield {"type": "message.chunk", "delta": "Thinking..."}
        
        available_tools = self.policy.get_available_tools_for_mode(session["mode"])
        if not available_tools:
            yield {"type": "message.chunk", "delta": "I can only answer questions in ASK mode."}
            yield {"type": "agent.completed", "summary": "Completed"}
            return
            
        tool_name = "edit_file"
        if tool_name in available_tools:
            level, reason = self.policy.check_permission(tool_name, {"path": "test.py"}, session_id)
            if level == PermissionLevel.CONFIRM:
                proposal_id = str(uuid.uuid4())
                session["pending_proposals"][proposal_id] = {"tool": tool_name, "args": {"path": "test.py"}}
                yield {"type": "edit.proposed", "proposal": {"id": proposal_id, "path": "test.py"}}
            else:
                yield {"type": "tool.request", "tool": tool_name, "arguments": {"path": "test.py"}, "permission": level.name}
                
        yield {"type": "agent.completed", "summary": "Turn finished"}
        
    def accept_proposal(self, session_id: str, proposal_id: str) -> dict:
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if proposal_id in session["pending_proposals"]:
                proposal = session["pending_proposals"].pop(proposal_id)
                return {"status": "accepted", "proposal": proposal}
        return {"status": "error", "message": "Invalid proposal"}
        
    def reject_proposal(self, session_id: str, proposal_id: str) -> dict:
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if proposal_id in session["pending_proposals"]:
                del session["pending_proposals"][proposal_id]
                return {"status": "rejected"}
        return {"status": "error", "message": "Invalid proposal"}
