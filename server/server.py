import asyncio
from collections import deque
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from .protocol import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelItem,
    ModelListResponse,
)
from .stream_adapter import (
    extract_tools_from_text,
    format_non_stream_response,
    format_sse_chunk,
    format_sse_done,
)
from server.providers.provider_adapter import parse_tool_response

# Custom log buffer to display clean server events inside Web Dashboard
class LogBufferHandler(logging.Handler):
    def __init__(self, maxlen: int = 150):
        super().__init__()
        self.buffer = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            # Suppress all internal dashboard polling & static assets from logs
            for noise in ["/api/logs", "/health", "/favicon.ico", "GET / HTTP", "GET /v1/models HTTP"]:
                if noise in msg:
                    return
            self.buffer.append({
                "time": time.strftime("%H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "msg": msg,
            })
        except Exception:
            pass


class EndpointFilter(logging.Filter):
    """Filters out all internal dashboard polling spam from terminal output."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for noise in ["/api/logs", "/health", "/favicon.ico", "GET / HTTP", "GET /v1/models HTTP"]:
            if noise in msg:
                return False
        return True


# Configure Logging
log_buffer = LogBufferHandler(maxlen=150)
log_buffer.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), log_buffer],
)
logger = logging.getLogger("WebChat2Local")

# Suppress noisy access logs in uvicorn
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())
logging.getLogger("uvicorn.access").addHandler(log_buffer)

app = FastAPI(
    title="WebChat2Local - ChatGPT Web to OpenAI API Gateway",
    description="Exposes ChatGPT Web as a standard OpenAI-compatible API for Cline, Roo Code, Continue, Codex, etc.",
    version="1.0.0",
)

# Enable CORS for local cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supported models list (DeepSeek, ChatGPT & Gemini Web)
AVAILABLE_MODELS = [
    "deepseek-chat",
    "deepseek-reasoner",
    "deepseek-v3",
    "deepseek-r1",
    "gpt-4o",
    "gpt-4o-mini",
    "chatgpt-4o-latest",
    "o1",
    "o1-mini",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "auto",
]


class ExtensionManager:
    """Manages WebSocket connections to multiple browser extension tabs (ChatGPT, Gemini) and routes request queues by model."""

    def __init__(self):
        # Map provider name ("ChatGPT", "Gemini") to connection details
        self.providers: Dict[str, Dict[str, Any]] = {}
        self.socket_to_provider: Dict[WebSocket, str] = {}
        self.pending_requests: Dict[str, asyncio.Queue] = {}
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "connected_at": None,
        }

    @property
    def is_connected(self) -> bool:
        return len(self.providers) > 0

    @property
    def active_providers(self) -> List[str]:
        return list(self.providers.keys())

    @property
    def client_info(self) -> Dict[str, Any]:
        """Returns primary or combined client info for backwards compatibility."""
        if not self.providers:
            return {}
        # Return first active provider's info
        first_key = list(self.providers.keys())[0]
        return self.providers[first_key].get("info", {})

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.stats["connected_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    def register_provider(self, websocket: WebSocket, info: dict):
        raw_name = str(info.get("provider", "ChatGPT")).lower()
        if "gemini" in raw_name:
            provider_name = "Gemini"
        elif "deepseek" in raw_name:
            provider_name = "DeepSeek"
        else:
            provider_name = "ChatGPT"

        self.providers[provider_name] = {
            "websocket": websocket,
            "info": info,
            "connected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "busy": False,
            "last_seen": time.time(),
        }
        self.socket_to_provider[websocket] = provider_name
        logger.info(f"Registered Provider '{provider_name}' via WebSocket. Active: {list(self.providers.keys())} (Info: {info})")

    def disconnect(self, websocket: Optional[WebSocket] = None):
        """Removes a specific socket without disconnecting other live providers."""
        if websocket is None:
            self.providers.clear()
            self.socket_to_provider.clear()
            logger.warning("All browser extensions disconnected.")
            return

        provider_name = self.socket_to_provider.pop(websocket, None)
        if provider_name and provider_name in self.providers:
            if self.providers[provider_name].get("websocket") == websocket:
                del self.providers[provider_name]
                logger.warning(f"Provider '{provider_name}' disconnected. Remaining active: {list(self.providers.keys())}")
        else:
            for name, p in list(self.providers.items()):
                if p.get("websocket") == websocket:
                    del self.providers[name]
                    logger.warning(f"Provider '{name}' disconnected.")

    def get_provider_for_model(self, model: str) -> Tuple[str, WebSocket]:
        """Intelligently selects the appropriate provider WebSocket based on model name, with automatic fallback."""
        if not self.providers:
            raise HTTPException(
                status_code=503,
                detail=(
                    "WebChat2Local Bridge: No active AI Web browser tabs connected.\n"
                    "1. Open Chrome/Edge.\n"
                    "2. Navigate to https://chatgpt.com (ChatGPT), https://gemini.google.com/app (Gemini), or https://chat.deepseek.com (DeepSeek).\n"
                    "3. Ensure WebChat2Local extension is loaded and active."
                ),
            )

        model_lower = (model or "").lower()

        # 1. Direct Gemini Routing
        if "gemini" in model_lower:
            if "Gemini" in self.providers:
                return "Gemini", self.providers["Gemini"]["websocket"]
            # Fallback if Gemini not connected but others are
            fallback = list(self.providers.keys())[0]
            logger.info(f"Model '{model}' requested Gemini, but Gemini tab not connected. Auto-fallback to [{fallback}].")
            return fallback, self.providers[fallback]["websocket"]

        # 2. Direct DeepSeek Routing
        if "deepseek" in model_lower:
            if "DeepSeek" in self.providers:
                return "DeepSeek", self.providers["DeepSeek"]["websocket"]
            # Fallback if DeepSeek not connected but others are
            fallback = list(self.providers.keys())[0]
            logger.info(f"Model '{model}' requested DeepSeek, but DeepSeek tab not connected. Auto-fallback to [{fallback}].")
            return fallback, self.providers[fallback]["websocket"]

        # 3. Direct ChatGPT Routing
        if any(prefix in model_lower for prefix in ["gpt", "chatgpt", "o1", "o3", "text-", "davinci"]):
            if "ChatGPT" in self.providers:
                return "ChatGPT", self.providers["ChatGPT"]["websocket"]
            # Fallback if ChatGPT not connected but others are
            fallback = list(self.providers.keys())[0]
            logger.info(f"Model '{model}' requested ChatGPT, but ChatGPT tab not connected. Auto-fallback to [{fallback}].")
            return fallback, self.providers[fallback]["websocket"]

        # 4. 'auto' or generic model: prefer idle provider, or first available
        if "ChatGPT" in self.providers and not self.providers["ChatGPT"].get("busy", False):
            return "ChatGPT", self.providers["ChatGPT"]["websocket"]
        if "Gemini" in self.providers and not self.providers["Gemini"].get("busy", False):
            return "Gemini", self.providers["Gemini"]["websocket"]
        if "DeepSeek" in self.providers and not self.providers["DeepSeek"].get("busy", False):
            return "DeepSeek", self.providers["DeepSeek"]["websocket"]

        # Default fallback to first connected provider
        first_provider = list(self.providers.keys())[0]
        return first_provider, self.providers[first_provider]["websocket"]

    async def dispatch_job(self, job_data: dict) -> asyncio.Queue:
        model = job_data.get("model", "auto")
        provider_name, target_socket = self.get_provider_for_model(model)

        req_id = job_data["request_id"]
        queue: asyncio.Queue = asyncio.Queue()
        self.pending_requests[req_id] = queue
        self.stats["total_requests"] += 1

        if provider_name in self.providers:
            self.providers[provider_name]["busy"] = True

        try:
            await target_socket.send_text(json.dumps(job_data))
            logger.info(f"Dispatched job {req_id} (model: {model}) -> [{provider_name}]")
        except Exception as e:
            self.pending_requests.pop(req_id, None)
            if provider_name in self.providers:
                self.providers[provider_name]["busy"] = False
            self.stats["failed_requests"] += 1
            logger.error(f"Failed to send job {req_id} to [{provider_name}]: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"Failed to communicate with [{provider_name}] browser extension: {str(e)}",
            )

        return queue

    def handle_message(self, websocket: WebSocket, data: dict):
        msg_type = data.get("type")
        req_id = data.get("request_id")

        if msg_type == "ready":
            info = data.get("info", {})
            self.register_provider(websocket, info)
            return

        if msg_type == "pong":
            return

        if not req_id or req_id not in self.pending_requests:
            logger.debug(f"Received message for unknown or finished request: {req_id}")
            return

        # Mark provider as idle when done or errored
        if msg_type in ["done", "error"]:
            provider_name = self.socket_to_provider.get(websocket)
            if provider_name and provider_name in self.providers:
                self.providers[provider_name]["busy"] = False

        queue = self.pending_requests[req_id]
        queue.put_nowait(data)


manager = ExtensionManager()


@app.get("/v1/models")
async def list_models():
    """Returns available models formatted as OpenAI model list."""
    models_data = [
        ModelItem(id=m, created=1710000000, owned_by="openai-web")
        for m in AVAILABLE_MODELS
    ]
    return ModelListResponse(data=models_data)


@app.get("/models")
async def list_models_alt():
    """Alias for /v1/models."""
    return await list_models()


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, raw_request: Request):
    """OpenAI compatible chat completions endpoint."""
    if not manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail=(
                "WebChat2Local Bridge: No active ChatGPT Web tab connected.\n"
                "1. Open Chrome/Edge.\n"
                "2. Navigate to https://chatgpt.com (Free Anonymous or Logged in).\n"
                "3. Ensure WebChat2Local extension is loaded and active."
            ),
        )

    req_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
    model_name = req.model or "gpt-4o"

    messages_payload = [
        {"role": m.role, "content": m.content, "name": m.name}
        for m in req.messages
    ]

    job_data = {
        "type": "chat_request",
        "request_id": req_id,
        "model": model_name,
        "messages": messages_payload,
        "stream": req.stream,
        "temperature": req.temperature,
    }

    # Extract requested tool names + definitions (forwarded to the browser so
    # the web model knows it MUST answer with XML tool tags).
    available_tool_names = []
    tool_definitions = []
    if req.tools:
        for t in req.tools:
            if isinstance(t, dict):
                fn = t.get("function", {})
                name = fn.get("name") if isinstance(fn, dict) else t.get("name")
                if name:
                    available_tool_names.append(name)
                    tool_definitions.append({
                        "name": name,
                        "description": (fn.get("description") if isinstance(fn, dict) else None) or "",
                        "parameters": (fn.get("parameters") if isinstance(fn, dict) else None) or {},
                    })

    if tool_definitions:
        job_data["tools"] = tool_definitions

    queue = await manager.dispatch_job(job_data)

    if req.stream:
        async def event_generator():
            yield format_sse_chunk(req_id, model_name, role="assistant")
            full_content = []
            try:
                while True:
                    try:
                        packet = await asyncio.wait_for(queue.get(), timeout=180.0)
                    except asyncio.TimeoutError:
                        logger.error(f"Request {req_id} timed out waiting for browser response.")
                        yield format_sse_chunk(
                            req_id,
                            model_name,
                            content_delta="\n\n[Error: AI Web response timed out]",
                        )
                        yield format_sse_done()
                        manager.stats["failed_requests"] += 1
                        break

                    p_type = packet.get("type")

                    if p_type == "chunk":
                        delta = packet.get("delta", "")
                        if delta:
                            full_content.append(delta)
                            yield format_sse_chunk(req_id, model_name, content_delta=delta)

                    elif p_type == "done":
                        full_text = packet.get("full_text", "") or "".join(full_content)
                        if available_tool_names:
                            adapted_text, tool_calls, finish_reason = parse_tool_response(full_text, available_tool_names)
                            if not full_content and adapted_text:
                                full_content.append(adapted_text)
                                yield format_sse_chunk(req_id, model_name, content_delta=adapted_text)

                            if tool_calls:
                                yield format_sse_chunk(
                                    req_id,
                                    model_name,
                                    finish_reason=finish_reason,
                                    tool_calls=tool_calls,
                                )
                            else:
                                yield format_sse_chunk(req_id, model_name, finish_reason=finish_reason)
                        else:
                            if not full_content and full_text:
                                full_content.append(full_text)
                                yield format_sse_chunk(req_id, model_name, content_delta=full_text)
                            finish_reason = packet.get("finish_reason", "stop")
                            yield format_sse_chunk(req_id, model_name, finish_reason=finish_reason)

                        yield format_sse_done()
                        manager.stats["successful_requests"] += 1
                        logger.info(f"Finished stream for {req_id} ({len(''.join(full_content))} chars).")
                        break

                    elif p_type == "error":
                        err_msg = packet.get("error", "Unknown error from AI Web")
                        logger.error(f"Error from browser on {req_id}: {err_msg}")
                        yield format_sse_chunk(
                            req_id,
                            model_name,
                            content_delta=f"\n\n[WebChat2Local Error: {err_msg}]",
                        )
                        yield format_sse_done()
                        manager.stats["failed_requests"] += 1
                        break

            finally:
                manager.pending_requests.pop(req_id, None)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
                "X-Accel-Buffering": "no",
            },
        )

    else:
        accumulated_text = []
        try:
            while True:
                try:
                    packet = await asyncio.wait_for(queue.get(), timeout=120.0)
                except asyncio.TimeoutError:
                    manager.stats["failed_requests"] += 1
                    raise HTTPException(
                        status_code=504,
                        detail="AI Web response timed out.",
                    )

                p_type = packet.get("type")

                if p_type == "chunk":
                    accumulated_text.append(packet.get("delta", ""))

                elif p_type == "done":
                    manager.stats["successful_requests"] += 1
                    final_text = packet.get("full_text") or "".join(accumulated_text)
                    tool_calls = None
                    finish_reason = packet.get("finish_reason", "stop")

                    if available_tool_names:
                        final_text, tool_calls, finish_reason = parse_tool_response(final_text, available_tool_names)

                    res_dict = format_non_stream_response(
                        req_id,
                        model_name,
                        final_text,
                        finish_reason=finish_reason,
                        tool_calls=tool_calls,
                    )
                    return JSONResponse(content=res_dict)

                elif p_type == "error":
                    manager.stats["failed_requests"] += 1
                    err_msg = packet.get("error", "Unknown error from AI Web")
                    raise HTTPException(status_code=500, detail=err_msg)

        finally:
            manager.pending_requests.pop(req_id, None)


async def _ws_keepalive(websocket: WebSocket):
    """Periodically ping the extension so proxies/browser keep the socket alive."""
    try:
        while True:
            await asyncio.sleep(20)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except Exception:
        pass


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for browser extension communication."""
    await manager.connect(websocket)
    keepalive = asyncio.create_task(_ws_keepalive(websocket))
    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
                manager.handle_message(websocket, data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received on WS: {raw_data[:100]}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)
    finally:
        keepalive.cancel()


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "browser_connected": manager.is_connected,
        "active_providers": manager.active_providers,
        "providers": {
            name: {
                "info": p.get("info", {}),
                "connected_at": p.get("connected_at"),
                "busy": p.get("busy", False),
            }
            for name, p in manager.providers.items()
        },
        "stats": manager.stats,
    }


@app.get("/api/logs")
async def get_logs():
    """Returns in-memory live server logs for the dashboard."""
    return list(log_buffer.buffer)



from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
import os
from server.tools.edit_engine import list_directory, read_file
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, Response

# We will serve static files from server/static
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

class SessionCreate(BaseModel):
    mode: str = "ASK"

class EditProposalRequest(BaseModel):
    path: str
    content: str

class TerminalRunRequest(BaseModel):
    command: str
    cwd: Optional[str] = None
    timeout: Optional[int] = 30
    
class AgentChatRequest(BaseModel):
    session_id: str
    prompt: str
    active_file: Optional[str] = None
    mode: Optional[str] = "ASK"
    model: Optional[str] = "auto"

class FileSaveRequest(BaseModel):
    path: str
    content: str

class FileCreateRequest(BaseModel):
    path: str
    content: Optional[str] = ""

class FileDeleteRequest(BaseModel):
    path: str
    revision: Optional[str] = None

# Store sessions and proposals in memory
SESSIONS = {}
PROPOSALS = {}

from server.agent.agent_orchestrator import AgentOrchestrator
orchestrator = AgentOrchestrator(dispatch_fn=manager.dispatch_job)

@app.get("/api/providers")
async def get_providers():
    return {
        "providers": [
            {
                "name": name,
                "active": True,
                "info": p.get("info", {}),
                "busy": p.get("busy", False),
            }
            for name, p in manager.providers.items()
        ] or [{"name": "No providers connected", "active": False}]
    }

@app.get("/api/providers/{provider_name}/health")
async def get_provider_health(provider_name: str):
    if provider_name in manager.providers:
        return {"status": "ok", "provider": provider_name, "active": True}
    return {"status": "offline", "provider": provider_name, "active": False}

@app.post("/api/sessions")
async def create_session(session: SessionCreate):
    session_id = orchestrator.create_session(mode=session.mode)
    SESSIONS[session_id] = {"mode": session.mode}
    return {"session_id": session_id, "mode": session.mode}

@app.post("/api/sessions/{session_id}/cancel")
async def cancel_session(session_id: str):
    if session_id in SESSIONS:
        del SESSIONS[session_id]
        orchestrator.cancel_session(session_id)
        return {"status": "cancelled"}
    raise HTTPException(status_code=404, detail="Session not found")

@app.post("/api/proposals/{proposal_id}/accept")
async def accept_proposal_endpoint(proposal_id: str):
    workspace = os.getenv("W2L_WORKSPACE", os.path.dirname(os.path.dirname(__file__)))
    # Check all active sessions in orchestrator
    for s_id in list(orchestrator.sessions.keys()):
        res = orchestrator.accept_proposal(s_id, proposal_id)
        if res.get("success"):
            return res
    if proposal_id in PROPOSALS:
        prop = PROPOSALS[proposal_id]
        prop["status"] = "accepted"
        if "base_revision" in prop and "new_content" in prop:
            from server.tools.edit_engine import apply_proposal
            res = apply_proposal(workspace, prop)
            return res
        return {"status": "accepted", "proposal_id": proposal_id}
    raise HTTPException(status_code=404, detail="Proposal not found")

@app.post("/api/proposals/{proposal_id}/reject")
async def reject_proposal_endpoint(proposal_id: str):
    for s_id in list(orchestrator.sessions.keys()):
        res = orchestrator.reject_proposal(s_id, proposal_id)
        if res.get("success"):
            return res
    if proposal_id in PROPOSALS:
        PROPOSALS[proposal_id]["status"] = "rejected"
        return {"status": "rejected", "proposal_id": proposal_id}
    raise HTTPException(status_code=404, detail="Proposal not found")

class WorkspaceSetRootRequest(BaseModel):
    path: str

@app.get("/api/workspace/info")
async def get_workspace_info():
    ws = orchestrator.workspace_root
    return {
        "workspace_root": ws,
        "workspace_name": os.path.basename(ws) or ws
    }

@app.post("/api/workspace/set_root")
async def set_workspace_root(req: WorkspaceSetRootRequest):
    target_path = os.path.abspath(req.path)
    if not os.path.exists(target_path):
        try:
            os.makedirs(target_path, exist_ok=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"無法建立指定目錄: {str(e)}")
            
    os.environ["W2L_WORKSPACE"] = target_path
    orchestrator.workspace_root = target_path
    orchestrator.context_manager.workspace_root = target_path
    orchestrator.tool_executor.workspace_root = target_path
    orchestrator.prompt_builder.workspace_root = target_path.replace("\\", "/")
    
    return {
        "success": True,
        "workspace_root": target_path,
        "workspace_name": os.path.basename(target_path) or target_path
    }

@app.get("/api/workspace/tree")
async def get_workspace_tree(path: Optional[str] = "."):
    workspace = orchestrator.workspace_root
    res = list_directory(workspace, path)
    res["path"] = path
    return res

@app.get("/api/workspace/file")
async def get_workspace_file(path: str):
    workspace = orchestrator.workspace_root
    return read_file(workspace, path)

@app.post("/api/workspace/file/save")
async def save_workspace_file(req: FileSaveRequest):
    workspace = orchestrator.workspace_root
    from server.tools.workspace_security import WorkspaceSecurityPolicy
    policy = WorkspaceSecurityPolicy(workspace)
    full_path = policy.validate_path(req.path)
    with open(full_path, "wb") as f:
        f.write(req.content.encode("utf-8"))
    from server.tools.edit_engine import compute_hash
    rev = compute_hash(req.content.encode("utf-8"))
    return {"success": True, "path": req.path, "revision": rev}

@app.post("/api/workspace/file/create")
async def create_workspace_file_endpoint(req: FileCreateRequest):
    workspace = orchestrator.workspace_root
    from server.tools.edit_engine import create_file
    res = create_file(workspace, req.path, req.content or "")
    return res

@app.post("/api/workspace/file/delete")
async def delete_workspace_file_endpoint(req: FileDeleteRequest):
    workspace = orchestrator.workspace_root
    from server.tools.edit_engine import delete_file, read_file
    rev = req.revision
    if not rev:
        try:
            f = read_file(workspace, req.path)
            rev = f["revision"]
        except Exception:
            rev = ""
    res = delete_file(workspace, req.path, rev)
    return res

@app.post("/api/workspace/edit")
async def edit_workspace_file(req: EditProposalRequest):
    import uuid
    proposal_id = str(uuid.uuid4())
    PROPOSALS[proposal_id] = {"path": req.path, "content": req.content, "status": "pending"}
    return {"proposal_id": proposal_id}

@app.post("/api/terminal/run")
async def terminal_run(req: TerminalRunRequest):
    import asyncio
    import time
    cmd = f'powershell -NoProfile -NonInteractive -Command "{req.command}"'
    start_time = time.time()
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=req.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=req.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            
        exit_code = proc.returncode
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        return {
            "exit_code": exit_code,
            "stdout": stdout.decode(errors="replace") if stdout else "",
            "stderr": stderr.decode(errors="replace") if stderr else "",
            "execution_time_ms": execution_time_ms
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/api/terminal/ws")
async def terminal_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Executed: {data}")
    except WebSocketDisconnect:
        pass

@app.post("/api/agent/chat")
async def agent_chat_endpoint(req: AgentChatRequest):
    async def event_generator():
        async for event in orchestrator.run_turn(req.session_id, req.prompt, req.active_file, req.model or "auto"):
            yield f"event: {event.get('type', 'message')}\ndata: {json.dumps(event)}\n\n"
            
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )

@app.get("/studio")
async def serve_studio():
    static_dir = os.path.join(os.path.dirname(__file__), "static", "studio")
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/studio.css")
async def serve_studio_css():
    static_file = os.path.join(os.path.dirname(__file__), "static", "studio", "studio.css")
    if os.path.exists(static_file):
        return FileResponse(static_file, media_type="text/css")
    raise HTTPException(status_code=404, detail="studio.css not found")

@app.get("/studio.js")
async def serve_studio_js():
    static_file = os.path.join(os.path.dirname(__file__), "static", "studio", "studio.js")
    if os.path.exists(static_file):
        return FileResponse(static_file, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="studio.js not found")

@app.get("/favicon.ico")
async def serve_favicon():
    return Response(status_code=204)

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    static_dir = os.path.join(os.path.dirname(__file__), "static", "studio")
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return "<h1>WebChat2Local Gateway & Studio Dashboard</h1><a href='/studio'>Open Studio</a>"
