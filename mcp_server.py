"""
WebChat Analysis MCP Server - Model Context Protocol (MCP) for Cline, Kilo, Cursor & Antigravity.
Exposes Google Gemini Web & ChatGPT Web as dedicated high-power sub-tools for deep code review,
repository architecture analysis, multimodal inspection, and live web search grounding.

Simplified configuration: purely for outsourced analysis and reasoning consultation.
Does not expose general local filesystem or shell manipulation tools.
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
from server.mcp.tools_system import doctor
from server.browser.gemini_direct import load_cookies
from server.bridge.ws_hub import hub

mcp = MCPServer(
    name="gemini-web-bridge",
    instructions=(
        "WebChat Analysis MCP Server (Gemini & ChatGPT). Provides massive context, "
        "thinking process, multimodal inspection, and live web search grounding as specialized "
        "outsourced code & task analysis sub-tools for AI agents."
    )
)

# ==========================================
# Core Universal WebChat Analysis Tools
# ==========================================

@mcp.tool()
async def webchat_analyze_code(
    files: Optional[List[str]] = None,
    code_snippet: Optional[str] = None,
    instructions: str = "Perform an in-depth code review, identify potential bugs, architectural flaws, security issues, and propose concrete improvements.",
    model: str = "webchat/auto",
) -> str:
    """
    Analyzes local project files or code snippets using WebChat (Gemini or ChatGPT).
    Use this when you need deep code review, architectural critique, bug finding, or refactoring advice.
    """
    return await analyze_code(
        files=files,
        code_snippet=code_snippet,
        instructions=instructions,
        model=model,
    )


@mcp.tool()
async def webchat_ask(
    prompt: str,
    model: str = "webchat/auto",
) -> str:
    """
    Consults WebChat (Gemini or ChatGPT) for complex architecture questions, hard debugging, or algorithm design.
    """
    return await ask_gemini(prompt=prompt, model=model)


@mcp.tool()
async def webchat_multimodal_inspect(
    image_path: str,
    prompt: str = "Analyze this image, screenshot, or UI mockup. Identify UI components, visual bugs, styling defects, or text contents.",
    model: str = "gemini-web/flash",
) -> str:
    """
    Inspects a local image file or screenshot (PNG, JPG, WEBP) using WebChat's vision capabilities.
    """
    return await inspect_image(image_path=image_path, prompt=prompt, model=model)


@mcp.tool()
async def webchat_web_search(
    query: str,
    instructions: Optional[str] = None,
) -> str:
    """
    Performs a real-time web search for latest documentation, APIs, or bug solutions.
    """
    return await web_search(query=query, instructions=instructions)


# ==========================================
# Backward Compatibility Aliases (Gemini)
# ==========================================

@mcp.tool()
async def gemini_analyze_code(
    files: Optional[List[str]] = None,
    code_snippet: Optional[str] = None,
    instructions: str = "Perform an in-depth code review, identify potential bugs, architectural flaws, security issues, and propose concrete improvements.",
    model: str = "gemini-web/pro",
) -> str:
    """Compatibility alias for webchat_analyze_code."""
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
    """Compatibility alias for webchat_ask."""
    return await ask_gemini(prompt=prompt, model=model)


@mcp.tool()
async def gemini_multimodal_inspect(
    image_path: str,
    prompt: str = "Analyze this image, screenshot, or UI mockup. Identify UI components, visual bugs, styling defects, or text contents.",
    model: str = "gemini-web/flash",
) -> str:
    """Compatibility alias for webchat_multimodal_inspect."""
    return await inspect_image(image_path=image_path, prompt=prompt, model=model)


@mcp.tool()
async def gemini_web_search(
    query: str,
    instructions: Optional[str] = None,
) -> str:
    """Compatibility alias for webchat_web_search."""
    return await web_search(query=query, instructions=instructions)


@mcp.tool()
async def ask_gemini_web(prompt: str, model: str = "gemini-web/pro") -> str:
    """Compatibility alias for webchat_ask."""
    return await ask_gemini(prompt=prompt, model=model)


@mcp.tool()
def webchat_models() -> str:
    """List the supported WebChat models available through this bridge."""
    return json.dumps({
        "models": [
            {"id": "webchat/auto", "name": "Universal WebChat (Auto Route)", "description": "Auto-dispatches to connected ChatGPT or Gemini tab"},
            {"id": "chatgpt-web/auto", "name": "ChatGPT Web (Guest / Auto)", "description": "Unlogged-in guest chat with auto-reset hygiene"},
            {"id": "chatgpt-web/gpt-4o-mini", "name": "ChatGPT Web (GPT-4o mini)", "description": "Default free unlogged-in model"},
            {"id": "gemini-web/pro", "name": "Google Gemini 2.5 Pro (Web)", "supports_thinking": True},
            {"id": "gemini-web/flash", "name": "Google Gemini 2.5 Flash (Web)", "supports_thinking": True},
        ]
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def gemini_web_models() -> str:
    """Compatibility alias for webchat_models."""
    return webchat_models()


@mcp.tool()
def get_webchat_status() -> str:
    """Get the real-time connection status of WebChat platforms (ChatGPT and Gemini)."""
    cookies = load_cookies()
    has_psid = bool(cookies.get("1psid"))
    browser_connected = hub.is_connected
    active_platform = hub.browser_info.get("platform", "None")
    return json.dumps({
        "bridge_status": "[READY] WebChat Analysis MCP Ready" if (has_psid or browser_connected) else "[WAITING] Connect browser or set cookies",
        "browser_connected": browser_connected,
        "browser_platform": active_platform,
        "gemini_cookie_configured": has_psid,
        "available_models": ["webchat/auto", "chatgpt-web/auto", "chatgpt-web/gpt-4o-mini", "gemini-web/pro", "gemini-web/flash"],
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def get_gemini_web_status() -> str:
    """Compatibility alias for get_webchat_status."""
    return get_webchat_status()


@mcp.tool()
def mcp_doctor() -> str:
    """Run full diagnostics on the WebChat analysis server, credentials, and environment."""
    res = doctor()
    res["browser_connected"] = hub.is_connected
    res["browser_platform"] = hub.browser_info.get("platform")
    return json.dumps(res, ensure_ascii=False, indent=2)


def print_doctor_report():
    print("=" * 60)
    print(" WebChat Analysis MCP Server - Diagnostic Report")
    print("=" * 60)
    cookies = load_cookies()
    has_psid = bool(cookies.get("1psid"))
    print(f"[*] Gemini Cookie Configured: {has_psid}")
    if has_psid:
        print(f"[*] 1PSID: {cookies['1psid'][:12]}... (Total length: {len(cookies['1psid'])})")
        print(f"[*] 1PSIDTS: {'Configured' if cookies.get('1psidts') else 'Not set'}")
    else:
        print("[-] Gemini Cookie: Not set (Gemini web extension or cookies needed for direct Gemini)")

    print(f"[*] Browser Extension Connected: {hub.is_connected}")
    if hub.is_connected:
        print(f"[*] Connected Platform: {hub.browser_info.get('platform')} ({hub.browser_info.get('page_url')})")
    else:
        print("[-] Browser Extension: Not currently connected to 127.0.0.1:8765")
        print("    (You can open https://chatgpt.com in Chrome/Edge with the extension loaded)")

    print("\n[*] Simplified Dedicated Analysis Tools:")
    print("    - webchat_analyze_code / gemini_analyze_code (Deep code review)")
    print("    - webchat_ask / gemini_ask (General reasoning consultation)")
    print("    - webchat_multimodal_inspect / gemini_multimodal_inspect (Visual inspection)")
    print("    - webchat_web_search / gemini_web_search (Live web search)")
    print("    - mcp_doctor (System self-diagnostics)")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="WebChat Analysis MCP Server")
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
        print(f"Starting WebChat Analysis MCP Server (SSE) on http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
