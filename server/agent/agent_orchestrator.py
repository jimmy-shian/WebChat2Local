import uuid
import json
import asyncio
import os
from typing import AsyncGenerator, Dict, Any, Optional, Callable
from server.core.constants import (
    ProviderName, ToolName, EventType, PermissionLevel, AgentMode, CANONICAL_TOOLS
)
from .permission_policy import ToolPermissionPolicy
from .context_manager import ContextBudgetManager
from .tool_executor import ToolExecutor
from server.providers.provider_adapter import format_tool_prompt, parse_tool_response
from server.tools.edit_engine import apply_proposal

from .prompt_builder import SystemPromptBuilder

class AgentOrchestrator:
    def __init__(self, dispatch_fn: Optional[Callable] = None, workspace_root: Optional[str] = None):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.policy = ToolPermissionPolicy()
        self.dispatch_fn = dispatch_fn
        self.workspace_root = workspace_root or os.getenv("W2L_WORKSPACE", os.getcwd())
        self.context_manager = ContextBudgetManager(self.workspace_root)
        self.tool_executor = ToolExecutor(self.workspace_root)
        self.prompt_builder = SystemPromptBuilder(self.workspace_root)
        
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
            yield {"type": EventType.AGENT_COMPLETED.value, "summary": "Session not found"}
            return
            
        session = self.sessions[session_id]
        if session["status"] == "cancelled":
            yield {"type": EventType.AGENT_COMPLETED.value, "summary": "Session cancelled"}
            return

        mode = session["mode"]
        if isinstance(mode, str):
            try:
                mode = AgentMode[mode]
            except Exception:
                mode = AgentMode.AGENT

        available_tools = self.policy.get_available_tools_for_mode(mode)
        
        ctx = self.context_manager.assemble_context(
            active_file=active_file,
            prompt=prompt
        )

        system_prompt = self.prompt_builder.build_system_prompt(active_file=active_file)
        full_user_prompt = self.prompt_builder.build_full_user_prompt(
            user_prompt=prompt,
            active_file=active_file,
            context_files=ctx.get("files", [])
        )

        # If no dispatch_fn provided (e.g. unit test mode), handle with fallback
        if not self.dispatch_fn:
            yield {"type": EventType.MESSAGE_CHUNK.value, "delta": f"處理中: {prompt[:30]}"}
            yield {"type": EventType.AGENT_COMPLETED.value, "summary": "Turn completed (test mode)"}
            return

        # Prepare Web LLM Job
        request_id = str(uuid.uuid4())
        job_data = {
            "type": "chat_request",
            "request_id": request_id,
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_user_prompt}
            ],
            "tools": [
                t for t in CANONICAL_TOOLS if t["name"] in available_tools
            ] if available_tools else []
        }

        try:
            queue = await self.dispatch_fn(job_data)
        except Exception as e:
            yield {"type": EventType.MESSAGE_CHUNK.value, "delta": f"\n[連線錯誤] 無法分派至 Web Provider: {str(e)}"}
            yield {"type": EventType.AGENT_COMPLETED.value, "summary": f"Dispatch failed: {str(e)}"}
            return

        full_response_text = ""
        # Stream chunks from Web Provider
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=120.0)
            except asyncio.TimeoutError:
                yield {"type": EventType.MESSAGE_CHUNK.value, "delta": "\n[超時] Web Provider 未在時間內回傳回應。"}
                break

            msg_type = msg.get("type")
            if msg_type == "chunk":
                chunk_text = msg.get("delta", "") or msg.get("text", "")
                if chunk_text:
                    full_response_text += chunk_text
                    yield {"type": EventType.MESSAGE_CHUNK.value, "delta": chunk_text}
                if msg.get("accumulated"):
                    full_response_text = msg.get("accumulated")
            elif msg_type == "done":
                done_full_text = msg.get("full_text", "")
                if done_full_text:
                    full_response_text = done_full_text
                break
            elif msg_type == "error":
                err_text = msg.get("error", "Unknown error")
                yield {"type": EventType.MESSAGE_CHUNK.value, "delta": f"\n[錯誤] {err_text}"}
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
                    
                    if t_name in [ToolName.CREATE_FILE.value, ToolName.EDIT_FILE.value]:
                        target_path = args.get("path")
                        if level == PermissionLevel.AUTO or self.policy.autopilot:
                            exec_res = await self.tool_executor.execute_tool(t_name, args)
                            if exec_res.get("success"):
                                yield {"type": EventType.TOOL_EXECUTED.value, "tool": t_name, "arguments": args, "result": exec_res}
                                yield {"type": EventType.MESSAGE_CHUNK.value, "delta": f"\n\n✅ 已自動執行 `{t_name}`: `{target_path}`"}
                            else:
                                yield {"type": EventType.MESSAGE_CHUNK.value, "delta": f"\n[執行失敗] {exec_res.get('error', '未知錯誤')}"}
                        else:
                            prop_id = str(uuid.uuid4())
                            prop = {
                                "proposal_id": prop_id,
                                "tool": t_name,
                                "path": target_path,
                                "arguments": args,
                                "new_content": args.get("content", ""),
                                "diff": args.get("content", "") or f"Edit on {target_path}"
                            }
                            session["pending_proposals"][prop_id] = prop
                            yield {"type": EventType.EDIT_PROPOSED.value, "proposal": prop}
                    
                    elif t_name == ToolName.RUN_COMMAND.value:
                        if level == PermissionLevel.AUTO or self.policy.autopilot:
                            exec_res = await self.tool_executor.execute_tool(t_name, args)
                            yield {"type": EventType.TOOL_EXECUTED.value, "tool": t_name, "arguments": args, "result": exec_res}
                        else:
                            yield {"type": EventType.TOOL_REQUEST.value, "tool": t_name, "arguments": args, "permission": level.value}

                    else:
                        exec_res = await self.tool_executor.execute_tool(t_name, args)
                        yield {"type": EventType.TOOL_EXECUTED.value, "tool": t_name, "arguments": args, "result": exec_res}

        yield {"type": EventType.AGENT_COMPLETED.value, "summary": "Turn completed"}
        
    def accept_proposal(self, session_id: str, proposal_id: str) -> dict:
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if proposal_id in session["pending_proposals"]:
                proposal = session["pending_proposals"].pop(proposal_id)
                t_name = proposal.get("tool", ToolName.EDIT_FILE.value)
                args = proposal.get("arguments", {})
                if t_name == ToolName.CREATE_FILE.value:
                    from server.tools.edit_engine import create_file
                    return create_file(self.workspace_root, proposal.get("path", args.get("path")), proposal.get("new_content", args.get("content", "")))
                elif t_name == ToolName.EDIT_FILE.value:
                    if "base_revision" in proposal and "new_content" in proposal:
                        return apply_proposal(self.workspace_root, proposal)
                    else:
                        from server.tools.edit_engine import edit_file, apply_proposal, read_file
                        path = proposal.get("path", args.get("path"))
                        edits = args.get("edits", [])
                        cur = read_file(self.workspace_root, path)
                        prop_res = edit_file(self.workspace_root, path, cur["revision"], edits)
                        if prop_res.get("success"):
                            return apply_proposal(self.workspace_root, prop_res)
                        return prop_res
                return {"success": True, "proposal": proposal}
        return {"success": False, "error": "PROPOSAL_NOT_FOUND"}
        
    def reject_proposal(self, session_id: str, proposal_id: str) -> dict:
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if proposal_id in session["pending_proposals"]:
                del session["pending_proposals"][proposal_id]
                return {"success": True, "status": "rejected"}
        return {"success": False, "error": "PROPOSAL_NOT_FOUND"}
