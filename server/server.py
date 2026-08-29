import asyncio
from collections import deque
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

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
    """Manages WebSocket connections to the browser extension and routes request queues."""

    def __init__(self):
        self.active_socket: Optional[WebSocket] = None
        self.connections: List[WebSocket] = []
        self.client_info: Dict[str, Any] = {}
        self.pending_requests: Dict[str, asyncio.Queue] = {}
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "connected_at": None,
        }

    @property
    def is_connected(self) -> bool:
        return self.active_socket is not None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)
        self.active_socket = websocket
        self.stats["connected_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Browser extension connected via WebSocket. ({len(self.connections)} live)")

    def disconnect(self, websocket: Optional[WebSocket] = None):
        """Remove a specific socket; fall back to another live connection if present."""
        if websocket is not None:
            self.connections = [c for c in self.connections if c is not websocket]
        else:
            self.connections = []
        if websocket is None or self.active_socket is websocket:
            self.active_socket = self.connections[-1] if self.connections else None
            self.client_info = {}
            if not self.active_socket:
                logger.warning("Browser extension disconnected.")

    async def dispatch_job(self, job_data: dict) -> asyncio.Queue:
        if not self.is_connected:
            raise HTTPException(
                status_code=503,
                detail=(
                    "No active ChatGPT Web session connected. Please open https://chatgpt.com in "
                    "Chrome/Edge with the WebChat2Local extension loaded."
                ),
            )

        req_id = job_data["request_id"]
        queue: asyncio.Queue = asyncio.Queue()
        self.pending_requests[req_id] = queue
        self.stats["total_requests"] += 1

        try:
            await self.active_socket.send_text(json.dumps(job_data))
            logger.info(f"Dispatched job {req_id} (model: {job_data.get('model')}) to browser.")
        except Exception as e:
            self.pending_requests.pop(req_id, None)
            self.stats["failed_requests"] += 1
            logger.error(f"Failed to send job {req_id} to browser: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"Failed to communicate with browser extension: {str(e)}",
            )

        return queue

    def handle_message(self, data: dict):
        msg_type = data.get("type")
        req_id = data.get("request_id")

        if msg_type == "ready":
            self.client_info = data.get("info", {})
            logger.info(f"Browser extension ready. Info: {self.client_info}")
            return

        if msg_type == "pong":
            return

        if not req_id or req_id not in self.pending_requests:
            logger.debug(f"Received message for unknown or finished request: {req_id}")
            return

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
                        if not full_content and full_text:
                            full_content.append(full_text)
                            yield format_sse_chunk(req_id, model_name, content_delta=full_text)

                        finish_reason = packet.get("finish_reason", "stop")
                        
                        # Tool calling adaptation for Cline / Roo Code
                        if available_tool_names:
                            tool_calls = extract_tools_from_text(full_text, available_tool_names)
                            if tool_calls:
                                finish_reason = "tool_calls"
                                yield format_sse_chunk(
                                    req_id,
                                    model_name,
                                    finish_reason=finish_reason,
                                    tool_calls=tool_calls,
                                )
                            else:
                                yield format_sse_chunk(req_id, model_name, finish_reason=finish_reason)
                        else:
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
                    finish_reason = packet.get("finish_reason", "stop")
                    tool_calls = None

                    if available_tool_names:
                        tool_calls = extract_tools_from_text(final_text, available_tool_names)
                        if tool_calls:
                            finish_reason = "tool_calls"

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
                manager.handle_message(data)
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
        "client_info": manager.client_info,
        "stats": manager.stats,
    }


@app.get("/api/logs")
async def get_logs():
    """Returns in-memory live server logs for the dashboard."""
    return list(log_buffer.buffer)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Compact single-page OpenDesign dashboard with live terminal logs."""
    return """
    <!DOCTYPE html>
    <html lang="zh-TW" class="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>WebChat2Local Gateway</title>
        <style>
            :root {
                --bg: #09090b;
                --surface: #121215;
                --surface-subtle: #18181b;
                --border: #27272a;
                --border-subtle: #1f1f23;
                --text-primary: #f4f4f5;
                --text-secondary: #a1a1aa;
                --text-muted: #71717a;
                --accent: #3b82f6;
                --accent-dim: rgba(59, 130, 246, 0.1);
                --success: #10b981;
                --success-dim: rgba(16, 185, 129, 0.12);
                --danger: #ef4444;
                --code-bg: #000000;
                --font-sans: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, "Noto Sans TC", sans-serif;
                --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            }

            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                background-color: var(--bg);
                color: var(--text-primary);
                font-family: var(--font-sans);
                font-size: 13px;
                line-height: 1.45;
                height: 100vh;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                padding: 16px 24px;
                -webkit-font-smoothing: antialiased;
            }

            .container {
                width: 100%;
                max-width: 1280px;
                margin: 0 auto;
                height: 100%;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }

            .header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                border-bottom: 1px solid var(--border);
                padding-bottom: 10px;
                flex-shrink: 0;
            }

            .header-title-group {
                display: flex;
                align-items: center;
                gap: 10px;
            }

            .title {
                font-size: 16px;
                font-weight: 600;
                color: var(--text-primary);
                letter-spacing: -0.02em;
            }

            .version-tag {
                font-family: var(--font-mono);
                font-size: 10.5px;
                background: var(--surface-subtle);
                color: var(--text-muted);
                padding: 2px 6px;
                border-radius: 4px;
                border: 1px solid var(--border);
            }

            .header-links a {
                color: var(--text-secondary);
                text-decoration: none;
                font-size: 12.5px;
                transition: color 0.15s;
            }
            .header-links a:hover {
                color: var(--text-primary);
            }

            /* Single Page Grid Layout */
            .main-layout {
                display: grid;
                grid-template-columns: 1fr 1.25fr;
                gap: 12px;
                flex: 1;
                min-height: 0; /* Important for inner scrolling */
            }

            .left-column {
                display: flex;
                flex-direction: column;
                gap: 10px;
                overflow-y: auto;
                padding-right: 4px;
            }

            .right-column {
                display: flex;
                flex-direction: column;
                gap: 10px;
                overflow-y: auto;
                padding-right: 4px;
            }

            .card {
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 6px;
                padding: 14px;
            }

            .section-label {
                font-size: 10.5px;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-muted);
                font-weight: 600;
                margin-bottom: 8px;
            }

            /* Status Row */
            .status-banner {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 8px 10px;
                border-radius: 4px;
                background: var(--surface-subtle);
                border: 1px solid var(--border-subtle);
                margin-bottom: 8px;
            }

            .status-indicator {
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 12px;
                font-weight: 500;
            }

            .status-dot {
                width: 6px;
                height: 6px;
                border-radius: 50%;
                background: var(--text-muted);
            }

            .status-dot.active {
                background: var(--success);
                box-shadow: 0 0 6px var(--success);
            }

            .status-dot.inactive {
                background: var(--danger);
            }

            .session-meta-grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 6px;
                font-size: 11.5px;
            }

            .meta-item {
                background: var(--bg);
                border: 1px solid var(--border-subtle);
                padding: 6px 8px;
                border-radius: 4px;
            }

            .meta-label {
                font-size: 10px;
                color: var(--text-muted);
                margin-bottom: 2px;
            }

            .meta-value {
                color: var(--text-primary);
                font-family: var(--font-mono);
                font-size: 11.5px;
                word-break: break-all;
            }

            /* Metrics */
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 6px;
            }

            .stat-box {
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 6px;
                padding: 10px;
            }

            .stat-title {
                font-size: 10px;
                color: var(--text-muted);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                margin-bottom: 2px;
            }

            .stat-number {
                font-family: var(--font-mono);
                font-size: 18px;
                font-weight: 600;
                color: var(--text-primary);
            }

            /* 1-Click Interactive Copy Cards */
            .config-list {
                display: flex;
                flex-direction: column;
                gap: 6px;
            }

            .config-item {
                display: flex;
                align-items: center;
                justify-content: space-between;
                background: var(--surface-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: 4px;
                padding: 8px 10px;
                cursor: pointer;
                user-select: none;
                transition: all 0.15s ease;
            }

            .config-item:hover {
                border-color: var(--border);
                background: #1c1c20;
            }

            .config-item.copied {
                border-color: var(--success);
                background: rgba(16, 185, 129, 0.08);
            }

            .config-label-group {
                display: flex;
                flex-direction: column;
                gap: 1px;
            }

            .config-key {
                font-size: 10px;
                color: var(--text-muted);
                text-transform: uppercase;
                letter-spacing: 0.03em;
            }

            .config-val {
                font-family: var(--font-mono);
                font-size: 12px;
                color: var(--text-primary);
                font-weight: 500;
            }

            .copy-hint {
                font-size: 10.5px;
                font-family: var(--font-mono);
                color: var(--text-muted);
                background: var(--bg);
                border: 1px solid var(--border-subtle);
                padding: 2px 6px;
                border-radius: 4px;
                transition: all 0.15s;
                white-space: nowrap;
            }

            .config-item:hover .copy-hint {
                color: var(--text-secondary);
                border-color: var(--border);
            }

            .config-item.copied .copy-hint {
                background: var(--success);
                color: #ffffff;
                border-color: var(--success);
            }

            /* Model Chips Dynamic Section */
            .model-section {
                background: var(--surface-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: 4px;
                padding: 8px 10px;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }

            .model-chips-grid {
                display: flex;
                flex-wrap: wrap;
                gap: 5px;
            }

            .model-chip {
                background: var(--bg);
                border: 1px solid var(--border);
                color: var(--text-primary);
                padding: 4px 8px;
                border-radius: 4px;
                font-family: var(--font-mono);
                font-size: 11px;
                cursor: pointer;
                transition: all 0.15s ease;
                display: inline-flex;
                align-items: center;
                gap: 4px;
                user-select: none;
            }

            .model-chip:hover {
                border-color: var(--text-secondary);
                background: var(--surface);
            }

            .model-chip.copied {
                border-color: var(--success);
                background: rgba(16, 185, 129, 0.12);
                color: var(--success);
            }

            /* Terminal Console Live Logs */
            .terminal-container {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-height: 240px;
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 6px;
                overflow: hidden;
            }

            .terminal-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                background: var(--surface-subtle);
                padding: 6px 10px;
                border-bottom: 1px solid var(--border);
                font-size: 11px;
            }

            .terminal-title {
                display: flex;
                align-items: center;
                gap: 6px;
                font-weight: 600;
                color: var(--text-secondary);
            }

            .terminal-tools {
                display: flex;
                align-items: center;
                gap: 6px;
            }

            .btn-action {
                background: var(--bg);
                border: 1px solid var(--border);
                color: var(--text-secondary);
                padding: 2px 8px;
                font-size: 10.5px;
                border-radius: 4px;
                cursor: pointer;
                transition: all 0.15s;
                font-family: var(--font-sans);
            }

            .btn-action:hover {
                color: var(--text-primary);
                border-color: var(--text-secondary);
            }

            .terminal-body {
                flex: 1;
                background: var(--code-bg);
                padding: 8px 10px;
                font-family: var(--font-mono);
                font-size: 11px;
                color: #e4e4e7;
                overflow-y: auto;
                line-height: 1.4;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .log-line {
                display: flex;
                gap: 8px;
                word-break: break-all;
            }

            .log-time {
                color: var(--text-muted);
                flex-shrink: 0;
            }

            .log-level {
                font-weight: 600;
                flex-shrink: 0;
            }

            .log-level.INFO { color: var(--success); }
            .log-level.WARNING { color: #f59e0b; }
            .log-level.ERROR { color: var(--danger); }

            .log-msg {
                color: #d4d4d8;
            }

            /* Endpoints Accordion */
            details.endpoint-item {
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 4px;
                overflow: hidden;
            }

            details.endpoint-item[open] {
                border-color: var(--text-muted);
            }

            summary.endpoint-summary {
                padding: 8px 12px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: space-between;
                user-select: none;
                list-style: none;
                font-size: 12px;
            }

            summary.endpoint-summary::-webkit-details-marker {
                display: none;
            }

            .endpoint-left {
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .method-badge {
                font-family: var(--font-mono);
                font-size: 10px;
                font-weight: 600;
                padding: 1px 5px;
                border-radius: 3px;
                background: var(--accent-dim);
                color: var(--accent);
                border: 1px solid rgba(59, 130, 246, 0.2);
            }

            .endpoint-path {
                font-family: var(--font-mono);
                color: var(--text-primary);
                font-weight: 500;
            }

            .endpoint-content {
                border-top: 1px solid var(--border-subtle);
                background: var(--bg);
                padding: 8px 10px;
            }

            pre.json-viewer {
                background: var(--code-bg);
                border: 1px solid var(--border-subtle);
                border-radius: 4px;
                padding: 8px;
                font-family: var(--font-mono);
                font-size: 11px;
                color: #e4e4e7;
                overflow-x: auto;
                max-height: 160px;
                line-height: 1.35;
            }

            .footer {
                display: flex;
                align-items: center;
                justify-content: space-between;
                font-size: 11px;
                color: var(--text-muted);
                border-top: 1px solid var(--border);
                padding-top: 6px;
                flex-shrink: 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Header -->
            <header class="header">
                <div class="header-title-group">
                    <h1 class="title">WebChat2Local</h1>
                    <span class="version-tag">Gateway</span>
                </div>
                <div class="header-links" style="display:flex;gap:12px;">
                    <a href="https://chat.deepseek.com" target="_blank" rel="noreferrer">DeepSeek 網頁 &rarr;</a>
                    <a href="https://chatgpt.com" target="_blank" rel="noreferrer">ChatGPT 網頁 &rarr;</a>
                    <a href="https://gemini.google.com" target="_blank" rel="noreferrer">Gemini 網頁 &rarr;</a>
                </div>
            </header>

            <!-- Main Single-Page 2-Column Grid -->
            <div class="main-layout">
                
                <!-- Left Column: Config & Session -->
                <div class="left-column">
                    <!-- Session Status Card -->
                    <div class="card">
                        <div class="section-label">會話狀態 (Session Status)</div>
                        <div class="status-banner">
                            <div class="status-indicator">
                                <span class="status-dot" id="status-dot"></span>
                                <span id="status-text">連線檢查中...</span>
                            </div>
                            <button class="btn-action" onclick="updateStatus(true)" style="padding:1px 6px;">手動整理</button>
                        </div>
                        <div class="session-meta-grid">
                            <div class="meta-item">
                                <div class="meta-label">帳號模式</div>
                                <div class="meta-value" id="user-email">-</div>
                            </div>
                            <div class="meta-item">
                                <div class="meta-label">方案等級</div>
                                <div class="meta-value" id="user-plan">-</div>
                            </div>
                        </div>
                    </div>

                    <!-- Metrics -->
                    <div class="stats-grid">
                        <div class="stat-box">
                            <div class="stat-title">總請求量</div>
                            <div class="stat-number" id="stat-total">0</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-title">成功傳輸</div>
                            <div class="stat-number" style="color:var(--success);" id="stat-success">0</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-title">失敗異常</div>
                            <div class="stat-number" style="color:var(--danger);" id="stat-failed">0</div>
                        </div>
                    </div>

                    <!-- Client Config (1-Click Copyable) -->
                    <div class="card">
                        <div class="section-label">本地客戶端參數 (點擊即可複製)</div>
                        <div class="config-list">
                            <div class="config-item" onclick="copyCardValue('OpenAI Compatible', this)">
                                <div class="config-label-group">
                                    <span class="config-key">Provider</span>
                                    <span class="config-val">OpenAI Compatible</span>
                                </div>
                                <span class="copy-hint">複製</span>
                            </div>

                            <div class="config-item" onclick="copyCardValue('http://127.0.0.1:8765/v1', this)">
                                <div class="config-label-group">
                                    <span class="config-key">Base URL</span>
                                    <span class="config-val">http://127.0.0.1:8765/v1</span>
                                </div>
                                <span class="copy-hint">複製</span>
                            </div>

                            <div class="config-item" onclick="copyCardValue('sk-local', this)">
                                <div class="config-label-group">
                                    <span class="config-key">API Key</span>
                                    <span class="config-val">sk-local</span>
                                </div>
                                <span class="copy-hint">複製</span>
                            </div>

                            <div class="model-section">
                                <span class="config-key">可用模型 (點擊任一模型即複製)</span>
                                <div class="model-chips-grid" id="model-chips-container">
                                    <span style="font-size:11px;color:var(--text-muted);">載入可用模型中...</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Right Column: Terminal Logs & Endpoints -->
                <div class="right-column">
                    <!-- Live Terminal Box -->
                    <div class="terminal-container">
                        <div class="terminal-header">
                            <div class="terminal-title">
                                <span class="status-dot active"></span>
                                <span>即時終端機日誌 (Live Console Logs)</span>
                            </div>
                            <div class="terminal-tools">
                                <button class="btn-action" onclick="fetchLogs()">重新整理</button>
                                <button class="btn-action" onclick="clearLogsUI()">清除畫面</button>
                                <button class="btn-action" onclick="copyAllLogs(this)">複製全部</button>
                            </div>
                        </div>
                        <div class="terminal-body" id="terminal-body">
                            <div class="log-line"><span class="log-time">[系統啟動]</span> <span class="log-msg">WebChat2Local 終端機連線已就緒...</span></div>
                        </div>
                    </div>

                    <!-- Collapsible Endpoints Inspection -->
                    <div style="display:flex;flex-direction:column;gap:6px;">
                        <!-- /v1/models inspection -->
                        <details class="endpoint-item" id="details-models" ontoggle="if(this.open) loadModelsData();">
                            <summary class="endpoint-summary">
                                <div class="endpoint-left">
                                    <span class="method-badge">GET</span>
                                    <span class="endpoint-path">/v1/models</span>
                                </div>
                                <span style="font-size:10.5px;color:var(--text-muted);font-family:var(--font-mono);">展開模型 JSON ▼</span>
                            </summary>
                            <div class="endpoint-content">
                                <pre class="json-viewer"><code id="models-json">載入中...</code></pre>
                            </div>
                        </details>

                        <!-- /health inspection -->
                        <details class="endpoint-item" id="details-health" ontoggle="if(this.open) loadHealthData();">
                            <summary class="endpoint-summary">
                                <div class="endpoint-left">
                                    <span class="method-badge">GET</span>
                                    <span class="endpoint-path">/health</span>
                                </div>
                                <span style="font-size:10.5px;color:var(--text-muted);font-family:var(--font-mono);">展開狀態 JSON ▼</span>
                            </summary>
                            <div class="endpoint-content">
                                <pre class="json-viewer"><code id="health-json">載入中...</code></pre>
                            </div>
                        </details>
                    </div>
                </div>

            </div>

            <footer class="footer">
                <span>WebChat2Local Gateway &bull; Local-first OpenAI Bridge</span>
                <span>健康檢查頻率: 每 60 秒 (或手動刷新)</span>
            </footer>
        </div>

        <script>
            function copyCardValue(text, el) {
                navigator.clipboard.writeText(text).then(() => {
                    const hint = el.querySelector('.copy-hint');
                    const origHint = hint ? hint.textContent : '';
                    el.classList.add('copied');
                    if (hint) hint.textContent = '已複製';
                    setTimeout(() => {
                        el.classList.remove('copied');
                        if (hint) hint.textContent = origHint;
                    }, 1500);
                });
            }

            function copyChipValue(text, chipEl) {
                navigator.clipboard.writeText(text).then(() => {
                    chipEl.classList.add('copied');
                    const origText = chipEl.textContent;
                    chipEl.textContent = text + ' ✓';
                    setTimeout(() => {
                        chipEl.classList.remove('copied');
                        chipEl.textContent = origText;
                    }, 1500);
                });
            }

            function copyAllLogs(btn) {
                const term = document.getElementById('terminal-body');
                navigator.clipboard.writeText(term.innerText).then(() => {
                    const orig = btn.textContent;
                    btn.textContent = '已複製';
                    setTimeout(() => { btn.textContent = orig; }, 1500);
                });
            }

            function clearLogsUI() {
                document.getElementById('terminal-body').innerHTML = '<div class="log-line"><span class="log-time">[清除]</span> <span class="log-msg">日誌畫面已重設</span></div>';
            }

            async function updateStatus(isManual = false) {
                try {
                    const resp = await fetch('/health');
                    if (!resp.ok) throw new Error('Health check error');
                    const data = await resp.json();

                    const dot = document.getElementById('status-dot');
                    const text = document.getElementById('status-text');
                    const email = document.getElementById('user-email');
                    const plan = document.getElementById('user-plan');
                    
                    document.getElementById('stat-total').textContent = data.stats?.total_requests || 0;
                    document.getElementById('stat-success').textContent = data.stats?.successful_requests || 0;
                    document.getElementById('stat-failed').textContent = data.stats?.failed_requests || 0;

                    if (data.browser_connected) {
                        dot.className = 'status-dot active';
                        text.textContent = '已連線 (Connected)';
                        text.style.color = 'var(--text-primary)';
                        email.textContent = data.client_info?.email || '已認證';
                        plan.textContent = data.client_info?.plan || 'Free / Plus';
                    } else {
                        dot.className = 'status-dot inactive';
                        text.textContent = '未連線 (等待 ChatGPT 網頁)';
                        text.style.color = 'var(--text-muted)';
                        email.textContent = '-';
                        plan.textContent = '-';
                    }

                    const healthEl = document.getElementById('health-json');
                    if (healthEl && document.getElementById('details-health').open) {
                        healthEl.textContent = JSON.stringify(data, null, 2);
                    }
                } catch (e) {
                    const dot = document.getElementById('status-dot');
                    const text = document.getElementById('status-text');
                    dot.className = 'status-dot inactive';
                    text.textContent = '伺服器通訊異常';
                }
            }

            async function fetchLogs() {
                try {
                    const resp = await fetch('/api/logs');
                    if (!resp.ok) return;
                    const logs = await resp.json();
                    const term = document.getElementById('terminal-body');
                    if (logs && logs.length > 0) {
                        term.innerHTML = logs.map(l => `
                            <div class="log-line">
                                <span class="log-time">[${l.time}]</span>
                                <span class="log-level ${l.level}">[${l.level}]</span>
                                <span class="log-msg">${l.msg.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</span>
                            </div>
                        `).join('');
                        term.scrollTop = term.scrollHeight;
                    }
                } catch (e) {}
            }

            async function fetchAndRenderModels() {
                const container = document.getElementById('model-chips-container');
                try {
                    const resp = await fetch('/v1/models');
                    const data = await resp.json();
                    if (data && data.data && data.data.length > 0) {
                        container.innerHTML = '';
                        data.data.forEach(m => {
                            const chip = document.createElement('button');
                            chip.className = 'model-chip';
                            chip.title = '點擊複製 Model ID: ' + m.id;
                            chip.textContent = m.id;
                            chip.onclick = () => copyChipValue(m.id, chip);
                            container.appendChild(chip);
                        });
                    }
                } catch (e) {
                    container.innerHTML = '<span style="font-size:11px;color:var(--danger);">無法讀取模型清單</span>';
                }
            }

            async function loadModelsData() {
                const el = document.getElementById('models-json');
                el.textContent = '載入中...';
                try {
                    const resp = await fetch('/v1/models');
                    const data = await resp.json();
                    el.textContent = JSON.stringify(data, null, 2);
                } catch (e) {
                    el.textContent = '無法獲取模型資料: ' + e.message;
                }
            }

            async function loadHealthData() {
                const el = document.getElementById('health-json');
                el.textContent = '載入中...';
                try {
                    const resp = await fetch('/health');
                    const data = await resp.json();
                    el.textContent = JSON.stringify(data, null, 2);
                } catch (e) {
                    el.textContent = '無法獲取健康狀態: ' + e.message;
                }
            }

            // Initial load
            fetchAndRenderModels();
            updateStatus();
            fetchLogs();

            // Low-frequency health check (every 120s) to avoid spam
            setInterval(() => {
                if (!document.hidden) {
                    updateStatus();
                }
            }, 120000);

            // Log update (every 15s when tab is active)
            setInterval(() => {
                if (!document.hidden) {
                    fetchLogs();
                }
            }, 15000);
        </script>
    </body>
    </html>
    """
