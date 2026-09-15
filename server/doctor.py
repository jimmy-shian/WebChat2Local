"""
Doctor / System Diagnostics Engine for Gemini Web to Local Bridge.
Modeled after codex-chatgpt-web/src/doctor.ts.
Performs end-to-end health checks on Python runtime, server gateway,
browser extension connection, Antigravity MCP integration, and Cline configs.
"""

import sys
import os
import json
import socket
from pathlib import Path
from typing import Dict, Any, List

from server.config import SERVER_HOST, SERVER_PORT, BASE_URL, get_workspace_root, VERSION
from server.model_catalog import AVAILABLE_GEMINI_WEB_ROUTES


def check_python_environment() -> Dict[str, Any]:
    """Checks Python executable, version, and virtual environment."""
    exe_path = sys.executable
    is_venv = hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
    return {
        "id": "python_env",
        "status": "ok",
        "message": f"Python {sys.version.split()[0]} running",
        "detail": f"Executable: {exe_path} (VirtualEnv: {is_venv})",
    }


def check_server_port() -> Dict[str, Any]:
    """Checks if the local bridge port is listening or reachable."""
    # Check if we are running inside the server process
    try:
        from server.bridge.ws_hub import hub
        return {
            "id": "server_port",
            "status": "ok",
            "message": f"Bridge Server is RUNNING at {BASE_URL}",
            "detail": f"Version: {VERSION}, Browser Connected: {hub.is_connected}, Active Tabs: {len(hub.active_connections)}",
        }
    except Exception:
        pass

    # External CLI socket probe
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    result = sock.connect_ex((SERVER_HOST, SERVER_PORT))
    sock.close()
    if result == 0:
        return {
            "id": "server_port",
            "status": "ok",
            "message": f"Bridge Server is listening on 127.0.0.1:{SERVER_PORT}",
            "detail": f"Base URL: {BASE_URL}/v1",
        }
    return {
        "id": "server_port",
        "status": "warning",
        "message": f"Bridge Server is OFFLINE (127.0.0.1:{SERVER_PORT})",
        "detail": "Run 'python run_server.py start' or double click 'start_server.bat' to launch.",
    }


def check_antigravity_integration() -> Dict[str, Any]:
    """Checks Antigravity .agents configuration and MCP registration."""
    workspace = get_workspace_root()
    mcp_config = workspace / ".agents" / "mcp_config.json"
    skill_file = workspace / ".agents" / "skills" / "gemini-bridge" / "SKILL.md"
    rule_file = workspace / ".agents" / "rules" / "gemini_rules.md"

    missing = []
    if not mcp_config.exists():
        missing.append(".agents/mcp_config.json")
    if not skill_file.exists():
        missing.append(".agents/skills/gemini-bridge/SKILL.md")
    if not rule_file.exists():
        missing.append(".agents/rules/gemini_rules.md")

    if not missing:
        return {
            "id": "antigravity_integration",
            "status": "ok",
            "message": "Google Antigravity MCP integration is fully configured",
            "detail": f"MCP Config: {mcp_config.name}, Skill: gemini-bridge, Rules: active",
        }
    return {
        "id": "antigravity_integration",
        "status": "warning",
        "message": f"Antigravity configuration incomplete (Missing: {', '.join(missing)})",
        "detail": "Run 'python setup_antigravity.py' to automatically install.",
    }


def check_extension_readiness() -> Dict[str, Any]:
    """Checks extension files and WebSocket endpoint."""
    workspace = get_workspace_root()
    ext_dir = workspace / "extension"
    manifest = ext_dir / "manifest.json"

    if manifest.exists():
        return {
            "id": "extension_readiness",
            "status": "ok",
            "message": "Chrome/Edge extension files ready",
            "detail": f"Extension directory: {ext_dir} (Load as unpacked extension in Chrome/Edge)",
        }
    return {
        "id": "extension_readiness",
        "status": "error",
        "message": "Extension directory missing manifest.json",
        "detail": str(manifest),
    }


def check_direct_transports() -> Dict[str, Any]:
    """Checks Gemini cookie and DeepSeek token direct-path readiness."""
    try:
        from server.browser.gemini_direct import is_configured as gemini_ok
        gemini_ready = bool(gemini_ok())
    except Exception:
        gemini_ready = False
    try:
        from server.browser.deepseek_direct import is_configured as ds_ok
        ds_ready = bool(ds_ok())
    except Exception:
        ds_ready = False
    if gemini_ready and ds_ready:
        return {"id": "direct_transports", "status": "ok",
                "message": "Gemini cookie + DeepSeek token both configured",
                "detail": "direct + deepseek-direct transports ready"}
    if gemini_ready or ds_ready:
        which = "Gemini cookie" if gemini_ready else "DeepSeek token"
        return {"id": "direct_transports", "status": "ok",
                "message": f"Direct transport ready ({which})",
                "detail": f"gemini={gemini_ready}, deepseek={ds_ready}"}
    return {"id": "direct_transports", "status": "warning",
            "message": "No direct transport configured (Gemini cookie / DeepSeek token missing)",
            "detail": "Set gemini_cookies.json or deepseek_token.json for browser-free calls."}


def run_doctor() -> Dict[str, Any]:
    """Runs all doctor checks and returns unified report."""
    checks = [
        check_python_environment(),
        check_server_port(),
        check_extension_readiness(),
        check_direct_transports(),
        check_antigravity_integration(),
    ]

    all_ok = all(c["status"] == "ok" for c in checks)
    has_error = any(c["status"] == "error" for c in checks)

    overall_status = "ok" if all_ok else ("error" if has_error else "warning")

    return {
        "overall_status": overall_status,
        "version": VERSION,
        "workspace_root": str(get_workspace_root()),
        "checks": checks,
        "available_models": [r.id for r in AVAILABLE_GEMINI_WEB_ROUTES],
    }
