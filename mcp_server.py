"""
Gemini Web Bridge - Model Context Protocol (MCP) Server for Google Antigravity & AI Clients.
Exposes Google Gemini Web (gemini.google.com) as an MCP tool, model bridge,
and full-harness local workspace tools.
"""

import sys
import os
import json
import httpx
from typing import Optional, Dict, Any
from mcp.server.mcpserver import MCPServer

from server.config import BASE_URL
from server.mcp.tools_filesystem import read_file, write_file, edit_file, list_dir, find_files
from server.mcp.tools_shell import run_command
from server.mcp.tools_search import grep_search, find_files as search_find_files
from server.mcp.tools_system import get_workspace_status, doctor

BRIDGE_API_URL = os.getenv("W2L_BRIDGE_URL", f"{BASE_URL}/v1")

mcp = MCPServer(
    name="gemini-web-bridge",
    instructions="Gemini Web Bridge MCP Server. Forwards prompts, reasoning, and coding tasks directly to Google Gemini Web (gemini.google.com), and provides local workspace tools."
)


# ==========================================
# Gemini Web Model Bridge Tools
# ==========================================

@mcp.tool()
def ask_gemini_web(prompt: str, model: str = "gemini-web/pro") -> str:
    """
    Forward a prompt, reasoning inquiry, or coding task to Google Gemini Web (gemini.google.com) and retrieve the AI response and thinking process.

    Args:
        prompt: The question, code request, or task description to send to Gemini Web.
        model: Model to use ('gemini-web/pro', 'gemini-web/flash', 'gemini-web/flash-thinking', 'gemini-web/ultra').
    """
    url = f"{BRIDGE_API_URL}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    try:
        with httpx.Client(timeout=180.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 503:
                return (
                    "【Gemini Web 尚未連線】\n"
                    "請先開啟 Chrome 或 Edge 瀏覽器，載入 WebChat2Local 擴充套件，並開啟 https://gemini.google.com 網頁。\n"
                    "網頁右下角顯示 🟢 連線後即可使用！"
                )
            if resp.status_code != 200:
                return f"[Gemini Bridge 錯誤 ({resp.status_code})]: {resp.text}"

            data = resp.json()
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            reasoning = message.get("reasoning_content")

            output_parts = []
            if reasoning:
                output_parts.append(f"### [Gemini Thinking / 思考過程]\n{reasoning}\n")
            if content:
                output_parts.append(f"### [Gemini Response / 回應]\n{content}")

            return "\n".join(output_parts) if output_parts else "【Gemini Web 回傳了空回應】"

    except httpx.ConnectError:
        return (
            "【本地伺服器未啟動】\n"
            "請先雙擊專案目錄下的 start_server.bat 或執行 python run_server.py start 啟動伺服器 (127.0.0.1:8765)。"
        )
    except Exception as e:
        return f"[連線異常]: {str(e)}"


@mcp.tool()
def get_gemini_web_status() -> str:
    """
    Get the real-time connection status of the Gemini Web browser extension and local bridge gateway.
    """
    url = f"{BRIDGE_API_URL}/status"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                is_conn = data.get("browser_connected", False)
                status_text = "[CONNECTED] Gemini Web Ready" if is_conn else "[DISCONNECTED] Browser not connected (Please open gemini.google.com)"
                return json.dumps({
                    "bridge_status": status_text,
                    "browser_connected": is_conn,
                    "active_tabs": data.get("active_tabs", 0),
                    "endpoint": BRIDGE_API_URL,
                    "available_models": ["gemini-web/pro", "gemini-web/flash", "gemini-web/flash-thinking", "gemini-web/ultra"]
                }, ensure_ascii=False, indent=2)
            return f"[伺服器回應異常 ({resp.status_code})]: {resp.text}"
    except httpx.ConnectError:
        return json.dumps({
            "bridge_status": "[DISCONNECTED] Local Server Not Running (127.0.0.1:8765)",
            "browser_connected": False,
            "hint": "Please run start_server.bat or python run_server.py start"
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"[診斷錯誤]: {str(e)}"


@mcp.tool()
def gemini_web_models() -> str:
    """
    List the supported Gemini Web models available through this bridge.
    """
    return json.dumps({
        "models": [
            {"id": "gemini-web/pro", "name": "Google Gemini 2.5 Pro (Web)", "supports_thinking": True},
            {"id": "gemini-web/flash", "name": "Google Gemini 2.5 Flash (Web)", "supports_thinking": True},
            {"id": "gemini-web/flash-thinking", "name": "Google Gemini Flash Thinking (Web)", "supports_thinking": True},
            {"id": "gemini-web/ultra", "name": "Google Gemini Advanced Ultra (Web)", "supports_thinking": True},
        ]
    }, ensure_ascii=False, indent=2)


# ==========================================
# Local Workspace Harness Tools
# ==========================================

@mcp.tool()
def mcp_read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    """Read contents of a file in the workspace."""
    res = read_file(path, start_line=start_line, end_line=end_line)
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp.tool()
def mcp_write_file(path: str, content: str, overwrite: bool = True) -> str:
    """Write or overwrite content to a file in the workspace."""
    res = write_file(path, content=content, overwrite=overwrite)
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp.tool()
def mcp_edit_file(path: str, search_target: str, replacement: str, allow_multiple: bool = False) -> str:
    """Perform exact text replacement within a file in the workspace."""
    res = edit_file(path, search_target=search_target, replacement=replacement, allow_multiple=allow_multiple)
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp.tool()
def mcp_list_dir(path: str = ".", max_depth: int = 1) -> str:
    """List entries inside a directory in the workspace."""
    res = list_dir(path=path, max_depth=max_depth)
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp.tool()
def mcp_find_files(pattern: str = "*", search_dir: str = ".", max_depth: int = 5, max_results: int = 50) -> str:
    """Find files by glob pattern inside the workspace."""
    res = search_find_files(
        pattern=pattern,
        search_dir=search_dir,
        max_depth=max_depth,
        max_results=max_results,
    )
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp.tool()
def mcp_grep_search(query: str, path: str = ".", case_sensitive: bool = False, max_results: int = 50) -> str:
    """Search for string or regex occurrences across workspace files."""
    res = grep_search(query=query, path=path, case_sensitive=case_sensitive, max_results=max_results)
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp.tool()
def mcp_run_command(command: str, cwd: Optional[str] = None, timeout_seconds: int = 60) -> str:
    """Execute a PowerShell command in the workspace."""
    res = run_command(command=command, cwd=cwd, timeout_seconds=timeout_seconds)
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp.tool()
def mcp_doctor() -> str:
    """Run full system diagnostics on the local bridge and environment."""
    res = doctor()
    return json.dumps(res, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
