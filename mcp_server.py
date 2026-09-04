"""
Gemini Analysis MCP Server - Model Context Protocol (MCP) for Cline, Kilo, Cursor & Antigravity.
Exposes Google Gemini Web as high-power sub-tools for deep code review, repository architecture
analysis, multimodal image inspection, and live Google web search.
"""

import sys
import os
import json
import argparse
from typing import Optional, List, Dict, Any
from mcp.server.mcpserver import MCPServer

from server.mcp.gemini_analysis_tools import (
    analyze_code,
    ask_gemini,
    inspect_image,
    web_search,
)
from server.mcp.tools_filesystem import read_file, write_file, edit_file, list_dir, find_files
from server.mcp.tools_shell import run_command
from server.mcp.tools_search import grep_search, find_files as search_find_files
from server.mcp.tools_system import get_workspace_status, doctor
from server.browser.gemini_direct import load_cookies, is_configured as direct_is_configured

mcp = MCPServer(
    name="gemini-web-bridge",
    instructions=(
        "Gemini Analysis MCP Server. Provides Google Gemini Web's massive context (1M+ tokens), "
        "thinking process, multimodal image inspection, and live web search grounding as specialized "
        "code & task analysis sub-tools for AI agents."
    )
)

# ==========================================
# Specialized Gemini Web Analysis Tools
# ==========================================

@mcp.tool()
async def gemini_analyze_code(
    files: Optional[List[str]] = None,
    code_snippet: Optional[str] = None,
    instructions: str = "Perform an in-depth code review, identify potential bugs, architectural flaws, security issues, and propose concrete improvements.",
    model: str = "gemini-web/pro",
) -> str:
    """
    Analyzes local project files, directory codebases, or raw diff snippets using Gemini's massive context window.
    Use this when you need deep code review, architectural critique, bug finding, or refactoring advice.
    """
    return await analyze_code(
        files=files,
        code_snippet=code_snippet,
        instructions=instructions,
        model=model,
    )


@mcp.tool()
async def gemini_ask(
    prompt: str,
    model: str = "gemini-web/pro",
) -> str:
    """
    Consults Gemini Web with deep thinking process for complex architecture questions, hard debugging, or algorithm design.
    """
    return await ask_gemini(prompt=prompt, model=model)


@mcp.tool()
async def gemini_multimodal_inspect(
    image_path: str,
    prompt: str = "Analyze this image, screenshot, or UI mockup. Identify UI components, visual bugs, styling defects, or text contents.",
    model: str = "gemini-web/flash",
) -> str:
    """
    Inspects a local image file or screenshot (PNG, JPG, WEBP) using Gemini Web's vision capabilities.
    """
    return await inspect_image(image_path=image_path, prompt=prompt, model=model)


@mcp.tool()
async def gemini_web_search(
    query: str,
    instructions: Optional[str] = None,
) -> str:
    """
    Performs a real-time web search using Google Search grounding for latest documentation, APIs, or bug solutions.
    """
    return await web_search(query=query, instructions=instructions)


@mcp.tool()
async def ask_gemini_web(prompt: str, model: str = "gemini-web/pro") -> str:
    """Backward compatibility tool alias for gemini_ask."""
    return await ask_gemini(prompt=prompt, model=model)


@mcp.tool()
def gemini_web_models() -> str:
    """List the supported Gemini Web models available through this bridge."""
    return json.dumps({
        "models": [
            {"id": "gemini-web/pro", "name": "Google Gemini 2.5 Pro (Web)", "supports_thinking": True},
            {"id": "gemini-web/flash", "name": "Google Gemini 2.5 Flash (Web)", "supports_thinking": True},
            {"id": "gemini-web/flash-thinking", "name": "Google Gemini Flash Thinking (Web)", "supports_thinking": True},
            {"id": "gemini-web/ultra", "name": "Google Gemini Advanced Ultra (Web)", "supports_thinking": True},
        ]
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def get_gemini_web_status() -> str:
    """Get the real-time connection status of the Gemini Web bridge and local credentials."""
    cookies = load_cookies()
    has_psid = bool(cookies.get("1psid"))
    return json.dumps({
        "bridge_status": "[READY] Gemini Web Analysis MCP Ready" if has_psid else "[CONFIG_NEEDED] Missing cookies",
        "cookie_configured": has_psid,
        "mode": "direct_mcp",
        "available_models": ["gemini-web/pro", "gemini-web/flash", "gemini-web/ultra"],
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
    """Execute a command in the workspace."""
    res = run_command(command=command, cwd=cwd, timeout_seconds=timeout_seconds)
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp.tool()
def mcp_doctor() -> str:
    """Run full diagnostics on the MCP server, credentials, and environment."""
    res = doctor()
    return json.dumps(res, ensure_ascii=False, indent=2)


def print_doctor_report():
    print("=" * 60)
    print(" Gemini Analysis MCP Server - Diagnostic Report")
    print("=" * 60)
    cookies = load_cookies()
    has_psid = bool(cookies.get("1psid"))
    print(f"[*] Cookie Configured: {has_psid}")
    if has_psid:
        print(f"[*] 1PSID: {cookies['1psid'][:12]}... (Total length: {len(cookies['1psid'])})")
        print(f"[*] 1PSIDTS: {'Configured' if cookies.get('1psidts') else 'Not set'}")
    else:
        print("[-] Warning: gemini_cookies.json not found or missing __Secure-1PSID.")
        print("    Run start_server.bat and click '自動抓取 Cookie' in the browser extension,")
        print("    or create gemini_cookies.json with your cookies.")

    print("\n[*] Available MCP Tools:")
    print("    - gemini_analyze_code (Deep file/codebase review)")
    print("    - gemini_ask (General reasoning and deep thinking consultation)")
    print("    - gemini_multimodal_inspect (Screenshot and visual UI analysis)")
    print("    - gemini_web_search (Google search grounding for live documentation)")
    print("    - mcp_read_file, mcp_write_file, mcp_edit_file, mcp_list_dir, mcp_grep_search, mcp_run_command")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Gemini Analysis MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="MCP transport mode (default: stdio)")
    parser.add_argument("--host", default="127.0.0.1", help="Host for SSE transport (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port for SSE transport (default: 8765)")
    parser.add_argument("--doctor", action="store_true", help="Print diagnostic report and exit")

    args = parser.parse_args()

    if args.doctor:
        print_doctor_report()
        return

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        import uvicorn
        app = mcp.sse_app()
        print(f"Starting Gemini Analysis MCP Server (SSE) on http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
