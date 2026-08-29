import uuid
import json
import asyncio
import os
from typing import AsyncGenerator, Dict, Any, Optional, Callable
from .permission_policy import AgentMode, ToolPermissionPolicy, PermissionLevel
from .context_manager import ContextBudgetManager
from server.providers.provider_adapter import format_tool_prompt, parse_tool_response
from server.tools.edit_engine import (
    read_file, edit_file, apply_proposal, create_file, delete_file, list_directory, grep_search, compute_hash
)

class AgentOrchestrator:
    def __init__(self, dispatch_fn: Optional[Callable] = None, workspace_root: Optional[str] = None):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.policy = ToolPermissionPolicy()
        self.dispatch_fn = dispatch_fn
        self.workspace_root = workspace_root or os.getenv("W2L_WORKSPACE", os.getcwd())
        self.context_manager = ContextBudgetManager(self.workspace_root)
        
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

        mode = session["mode"]
        if isinstance(mode, str):
            try:
                mode = AgentMode[mode]
            except Exception:
                mode = AgentMode.AGENT

        available_tools = self.policy.get_available_tools_for_mode(mode)
        
        # 1. If in ASK mode (pure Q&A, no tools), dispatch directly
        # 2. Assemble context
        ctx = self.context_manager.assemble_context(
            active_file=active_file,
            prompt=prompt
        )

        full_prompt = prompt
        if ctx.get("files"):
            file_ctx = "\n".join([f"=== 檔案 {f['path']} ===\n{f['content']}\n" for f in ctx["files"]])
            full_prompt = f"{file_ctx}\n\n使用者需求: {prompt}"

        # If no dispatch_fn provided (e.g. unit test mode), handle with fallback
        if not self.dispatch_fn:
            yield {"type": "message.chunk", "delta": f"處理中: {prompt[:30]}"}
            yield {"type": "agent.completed", "summary": "Turn completed (test mode)"}
            return

        # Prepare Web LLM Job
        request_id = str(uuid.uuid4())
        job_data = {
            "request_id": request_id,
            "model": model,
            "messages": [
                {"role": "user", "content": full_prompt}
            ],
            "tools": [
                {"name": t, "description": f"Tool {t}", "parameters": {}} for t in available_tools
            ] if available_tools else []
        }

        try:
            queue = await self.dispatch_fn(job_data)
        except Exception as e:
            yield {"type": "message.chunk", "delta": f"\n[連線錯誤] 無法分派至 Web Provider: {str(e)}"}
            yield {"type": "agent.completed", "summary": f"Dispatch failed: {str(e)}"}
            return

        full_response_text = ""
        # Stream chunks from Web Provider
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=120.0)
            except asyncio.TimeoutError:
                yield {"type": "message.chunk", "delta": "\n[超時] Web Provider 未在時間內回傳回應。"}
                break

            msg_type = msg.get("type")
            if msg_type == "chunk":
                chunk_text = msg.get("text", "")
                full_response_text += chunk_text
                yield {"type": "message.chunk", "delta": chunk_text}
            elif msg_type == "done":
                break
            elif msg_type == "error":
                err_text = msg.get("error", "Unknown error")
                yield {"type": "message.chunk", "delta": f"\n[錯誤] {err_text}"}
                break

        # Parse Tool Response
        if available_tools:
            adapted_content, tool_calls, finish_reason = parse_tool_response(full_response_text, available_tools)
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    t_name = fn.get("name")
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except Exception:
                        args = {}

                    level, reason = self.policy.check_permission(t_name, args, session_id)
                    
                    if t_name == "create_file":
                        target_path = args.get("path")
                        target_content = args.get("content", "")
                        if level == PermissionLevel.AUTO or self.policy.autopilot:
                            res = create_file(self.workspace_root, target_path, target_content)
                            yield {"type": "message.chunk", "delta": f"\n\n✅ 已自動建立檔案: `{target_path}`"}
                        else:
                            prop_id = str(uuid.uuid4())
                            prop = {
                                "proposal_id": prop_id,
                                "path": target_path,
                                "new_content": target_content,
                                "diff": f"+ {target_content[:200]}"
                            }
                            session["pending_proposals"][prop_id] = prop
                            yield {"type": "edit.proposed", "proposal": prop}
                    
                    elif t_name == "edit_file":
                        target_path = args.get("path")
                        edits = args.get("edits", [])
                        rev = args.get("revision")
                        if not rev:
                            try:
                                cur_f = read_file(self.workspace_root, target_path)
                                rev = cur_f["revision"]
                            except Exception:
                                rev = "sha256:unknown"
                        
                        prop_res = edit_file(self.workspace_root, target_path, rev, edits)
                        if prop_res.get("success"):
                            prop_id = prop_res["proposal_id"]
                            session["pending_proposals"][prop_id] = prop_res
                            yield {"type": "edit.proposed", "proposal": prop_res}
                        else:
                            yield {"type": "message.chunk", "delta": f"\n[編輯失敗] {prop_res.get('message', '未知錯誤')}"}
                    
                    elif t_name == "run_command":
                        cmd = args.get("command")
                        yield {"type": "tool.request", "tool": "run_command", "arguments": args, "permission": level.name}

        yield {"type": "agent.completed", "summary": "Turn completed"}
        
    def accept_proposal(self, session_id: str, proposal_id: str) -> dict:
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if proposal_id in session["pending_proposals"]:
                proposal = session["pending_proposals"].pop(proposal_id)
                # Apply proposal to disk
                if "base_revision" in proposal and "new_content" in proposal:
                    return apply_proposal(self.workspace_root, proposal)
                elif "new_content" in proposal and "path" in proposal:
                    # Direct create/write
                    return create_file(self.workspace_root, proposal["path"], proposal["new_content"])
                return {"success": True, "proposal": proposal}
        return {"success": False, "error": "PROPOSAL_NOT_FOUND"}
        
    def reject_proposal(self, session_id: str, proposal_id: str) -> dict:
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if proposal_id in session["pending_proposals"]:
                del session["pending_proposals"][proposal_id]
                return {"success": True, "status": "rejected"}
        return {"success": False, "error": "PROPOSAL_NOT_FOUND"}
