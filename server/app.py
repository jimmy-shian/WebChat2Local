"""
FastAPI Application for Gemini Web to Local Bridge.
Exposes OpenAI Chat Completions, Codex/Antigravity Responses API, WebSocket hub, and Web Dashboard.
Modeled after codex-chatgpt-web/src/server.ts.
"""

import os
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.config import MODEL_CATALOG, BASE_URL, VERSION, DIRECT_FALLBACK_ENABLED, DIRECT_ONLY
from server.protocol import ChatCompletionRequest, ResponsesRequest
from server.bridge.ws_hub import hub
from server.browser.gemini_direct import (
    is_configured as direct_is_configured,
    stream_generate,
    save_cookies,
)
from server.bridge.session_manager import SessionManager
from server.bridge.stream_adapter import (
    stream_openai_completions,
    stream_responses_api,
    collect_complete_response,
)
from server.doctor import run_doctor
from server.mcp.tools_system import get_workspace_status


app = FastAPI(
    title="Gemini Web to Local Bridge",
    description="Bridge Google Gemini Web to local development environments, MCP, and Google Antigravity.",
    version=VERSION,
)

# Enable CORS for all local tools and browser extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"


# ==========================================
# OpenAI & Responses API Endpoints
# ==========================================

@app.get("/v1/models")
@app.get("/models")
async def list_models():
    """Lists supported Gemini Web models."""
    return {"object": "list", "data": MODEL_CATALOG}


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    """
    OpenAI-compatible Chat Completions API endpoint.
    Supports real-time SSE streaming (stream=true) with reasoning_content deltas,
    and structured JSON return (stream=false).
    """
    # 1. Compile multi-turn messages into Gemini prompt
    compiled_prompt = SessionManager.compile_prompt(
        messages=req.messages,
        tools=req.tools,
        enable_mcp_system=False
    )
    tool_names = []
    for tool in req.tools or []:
        fn = tool.get("function", tool) if isinstance(tool, dict) else {}
        if isinstance(fn, dict) and fn.get("name"):
            tool_names.append(str(fn["name"]))

    # 2. Dispatch turn. Cookie-authenticated HTTP is deliberately preferred so
    # API clients never depend on a browser tab, DOM, canvas rendering, or the
    # extension's WebSocket transport. The extension remains an opt-in fallback.
    if DIRECT_ONLY and DIRECT_FALLBACK_ENABLED and direct_is_configured():
        turn_generator = stream_generate(prompt=compiled_prompt, model=req.model)
    elif hub.is_connected:
        turn_generator = hub.execute_turn(
            prompt=compiled_prompt,
            model=req.model,
        )
    elif DIRECT_FALLBACK_ENABLED and direct_is_configured():
        turn_generator = stream_generate(
            prompt=compiled_prompt,
            model=req.model,
        )
    else:
        raise HTTPException(
            status_code=503,
            detail=(
                "Gemini Web browser extension is not connected and no direct "
                "cookie is configured. Open https://gemini.google.com in Chrome/Edge, "
                "or set GEMINI_1PSID / create gemini_cookies.json."
            )
        )

    if req.stream:
        return StreamingResponse(
            stream_openai_completions(
                turn_generator,
                model=req.model,
                available_tool_names=tool_names,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        resp = await collect_complete_response(
            turn_generator,
            model=req.model,
            available_tool_names=tool_names,
        )
        return resp.model_dump()


@app.post("/v1/responses")
@app.post("/responses")
async def responses_api(req: ResponsesRequest):
    """
    Codex & Google Antigravity Responses API endpoint with SSE streaming.
    """
    if isinstance(req.input, str):
        prompt_text = SessionManager.compile_prompt(messages=[{"role": "user", "content": req.input}], tools=req.tools)
    elif isinstance(req.input, list):
        normalized = []
        for item in req.input:
            if isinstance(item, dict) and item.get("role"):
                normalized.append(item)
            elif isinstance(item, str):
                normalized.append({"role": "user", "content": item})
            else:
                normalized.append({"role": "user", "content": str(item)})
        prompt_text = SessionManager.compile_prompt(messages=normalized, tools=req.tools)
    else:
        prompt_text = SessionManager.compile_prompt(messages=[{"role": "user", "content": str(req.input)}], tools=req.tools)

    if DIRECT_ONLY and DIRECT_FALLBACK_ENABLED and direct_is_configured():
        turn_generator = stream_generate(prompt=prompt_text, model=req.model)
    elif hub.is_connected:
        turn_generator = hub.execute_turn(prompt=prompt_text, model=req.model)
    elif DIRECT_FALLBACK_ENABLED and direct_is_configured():
        turn_generator = stream_generate(prompt=prompt_text, model=req.model)
    else:
        raise HTTPException(
            status_code=503,
            detail="Gemini Web browser extension is not connected and no direct cookie is configured."
        )

    return StreamingResponse(
        stream_responses_api(turn_generator, model=req.model),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/v1/cookies")
async def save_cookies_endpoint(payload: dict):
    """
    Persist the __Secure-1PSID / __Secure-1PSIDTS cookies sent by the browser
    extension, so the direct (cookie-based) Gemini path can use them.
    """
    one_psid = str(payload.get("1psid", "") or payload.get("__Secure-1PSID", "")).strip()
    one_psidts = str(payload.get("1psidts", "") or payload.get("__Secure-1PSIDTS", "")).strip()

    if not one_psid:
        raise HTTPException(status_code=400, detail="1psid is required.")

    if not save_cookies(one_psid, one_psidts):
        raise HTTPException(status_code=500, detail="Failed to write gemini_cookies.json.")

    return {"status": "ok", "configured": direct_is_configured()}


# ==========================================
# Diagnostics, Status & Management
# ==========================================

@app.get("/v1/health")
@app.get("/health")
@app.get("/healthz")
async def health_check():
    return {
        "status": "ok",
        "service": "gemini-web-to-local",
        "version": VERSION,
        "browser_connected": hub.is_connected,
        "bridge_url": BASE_URL,
        "accepting_turns": not hub.is_draining,
    }


@app.get("/v1/status")
@app.get("/status")
async def system_status():
    status = hub.get_status()
    status["workspace"] = get_workspace_status()
    status["doctor"] = run_doctor()
    return status


@app.get("/v1/doctor")
async def get_doctor_report():
    return run_doctor()


@app.get("/v1/logs")
@app.get("/logs")
async def get_logs(limit: int = 100):
    return {"logs": hub.logs.get_logs(limit=limit)}


@app.post("/v1/drain")
async def drain_server(enable: bool = True):
    hub.is_draining = enable
    hub.logs.log("INFO", "SERVER", f"Server drain mode set to {enable}")
    return {"status": "ok", "draining": hub.is_draining, "active_turns": 1 if hub.active_turn_id else 0}


@app.post("/v1/reset")
@app.post("/reset")
async def reset_server_state():
    """Force cancel any running turns, broadcast reset to extension, and clear locks."""
    await hub.reset_all_turns()
    return {"status": "ok", "message": "Browser state and turn locks have been reset."}


@app.post("/v1/dev/turn")
async def dev_synthetic_turn(payload: dict):
    """Synthetic prompt tester for the web dashboard."""
    prompt = payload.get("prompt", "")
    model = payload.get("model", "gemini-web/pro")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required.")

    if not hub.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Gemini Web 瀏覽器擴充套件尚未連線。請開啟 https://gemini.google.com。"
        )

    turn_gen = hub.execute_turn(prompt=prompt, model=model)
    return StreamingResponse(
        stream_openai_completions(turn_gen, model=model),
        media_type="text/event-stream"
    )


# ==========================================
# Browser Extension WebSocket Connection
# ==========================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await hub.register_connection(websocket)
    try:
        while True:
            raw_msg = await websocket.receive_text()
            try:
                import json
                data = json.loads(raw_msg)
                await hub.handle_incoming_message(data)
            except Exception as e:
                hub.logs.log("ERROR", "WS", f"Error parsing incoming WS message: {e}")
    except WebSocketDisconnect:
        hub.unregister_connection(websocket)
    except Exception as e:
        hub.unregister_connection(websocket)
        hub.logs.log("WARN", "WS", f"WebSocket exception: {e}")


# ==========================================
# Dashboard & Static Assets
# ==========================================

@app.get("/")
async def serve_dashboard():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": f"Gemini Web to Local Bridge API Running (v{VERSION}). Open /v1/status for diagnostics."}


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
