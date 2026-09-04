"""
Dedicated Gemini Web Analysis Tools for Model Context Protocol (MCP).
Allows external primary AI models (Claude 3.7, GPT-4o, DeepSeek, etc.) in Cline, Kilo,
Cursor, and Antigravity to harness Gemini Web's massive context, thinking process,
multimodal perception, and Google search grounding as specialized sub-tools.
"""

import os
import io
import mimetypes
from typing import List, Optional, Dict, Any

from server.browser.gemini_direct import direct_engine


async def analyze_code(
    files: Optional[List[str]] = None,
    code_snippet: Optional[str] = None,
    instructions: str = "Perform an in-depth code review, identify potential bugs, architectural flaws, security issues, and propose concrete improvements.",
    model: str = "gemini-web/pro",
) -> str:
    """
    Analyzes local source files or raw code snippets using Gemini Web's massive context window.

    Args:
        files: List of file paths to inspect and analyze (relative or absolute).
        code_snippet: Optional raw code, diff, or log text to analyze alongside or instead of files.
        instructions: Specific review directives or questions about the code.
        model: Model to use ('gemini-web/pro' for deep reasoning, 'gemini-web/flash' for fast check).
    """
    file_blocks = []
    if files:
        for fpath in files:
            path_str = str(fpath).strip()
            if not path_str:
                continue
            if not os.path.exists(path_str):
                file_blocks.append(f"### File: `{path_str}`\n[Warning: File does not exist or cannot be accessed]")
                continue

            try:
                with open(path_str, "r", encoding="utf-8", errors="replace") as f:
                    file_content = f.read()
                file_blocks.append(f"### File: `{path_str}` ({len(file_content):,} chars)\n```\n{file_content}\n```")
            except Exception as err:
                file_blocks.append(f"### File: `{path_str}`\n[Read Error: {err}]")

    prompt_parts = [
        "## TASK DIRECTIVE",
        instructions.strip(),
        "",
        "## CODE CONTEXT FOR ANALYSIS",
    ]

    if file_blocks:
        prompt_parts.extend(file_blocks)
    if code_snippet and code_snippet.strip():
        prompt_parts.append(f"### Additional Code / Diff Snippet:\n```\n{code_snippet.strip()}\n```")

    if not file_blocks and not (code_snippet and code_snippet.strip()):
        return "[Error]: Please provide at least one valid file path in 'files' or code in 'code_snippet' to analyze."

    full_prompt = "\n".join(prompt_parts)

    try:
        res = await direct_engine.generate_analysis(prompt=full_prompt, model=model)
        output = []
        if res.get("thought"):
            output.append(f"### [Gemini Reasoning / 思考過程]\n{res['thought']}\n")
        output.append(f"### [Gemini Code Review / 代碼審查報告]\n{res.get('text', '')}")
        return "\n".join(output)
    except Exception as e:
        return f"[Gemini Analysis Error]: {e}"


async def ask_gemini(
    prompt: str,
    model: str = "gemini-web/pro",
) -> str:
    """
    Consults Gemini Web for general problem solving, complex architecture questions, or deep reasoning.

    Args:
        prompt: The query or reasoning prompt to send to Gemini.
        model: Model to use ('gemini-web/pro', 'gemini-web/flash', 'gemini-web/ultra').
    """
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return "[Error]: Prompt cannot be empty."

    try:
        res = await direct_engine.generate_analysis(prompt=clean_prompt, model=model)
        output = []
        if res.get("thought"):
            output.append(f"### [Gemini Reasoning / 思考過程]\n{res['thought']}\n")
        output.append(f"### [Gemini Response / 回應]\n{res.get('text', '')}")
        if res.get("citations"):
            output.append("\n### [Sources / 參考來源]\n" + "\n".join(f"- {c}" for c in res["citations"]))
        return "\n".join(output)
    except Exception as e:
        return f"[Gemini Ask Error]: {e}"


async def inspect_image(
    image_path: str,
    prompt: str = "Analyze this image, screenshot, or UI mockup. Identify UI components, visual bugs, styling defects, or text contents.",
    model: str = "gemini-web/flash",
) -> str:
    """
    Inspects a local image or screenshot using Gemini Web's multimodal capabilities.

    Args:
        image_path: Absolute or relative path to the image file (PNG, JPG, WEBP, GIF).
        prompt: Specific question or inspection instructions for the image.
        model: Model to use (defaults to 'gemini-web/flash' for quick vision analysis).
    """
    if not os.path.exists(image_path):
        return f"[Error]: Image file '{image_path}' not found on local filesystem."

    try:
        with open(image_path, "rb") as f:
            raw_bytes = f.read()

        bio = io.BytesIO(raw_bytes)
        ext = os.path.splitext(image_path)[1].lower()
        mime_type, _ = mimetypes.guess_type(image_path)
        bio.name = f"image{ext or '.png'}"
        bio.content_type = mime_type or "image/png"

        res = await direct_engine.generate_analysis(
            prompt=prompt.strip(),
            model=model,
            files=[bio],
        )
        output = []
        if res.get("thought"):
            output.append(f"### [Gemini Vision Reasoning / 視覺思考過程]\n{res['thought']}\n")
        output.append(f"### [Gemini Vision Analysis / 視覺分析結果]\n{res.get('text', '')}")
        return "\n".join(output)
    except Exception as e:
        return f"[Gemini Vision Error]: {e}"


async def web_search(
    query: str,
    instructions: Optional[str] = None,
) -> str:
    """
    Searches the live web using Gemini Web's Google search grounding for up-to-date technical docs.

    Args:
        query: The search keywords or error message to query.
        instructions: Optional specific focus or formatting instructions.
    """
    search_prompt = (
        f"Please perform a real-time web search for the following query and provide an accurate, up-to-date technical summary:\n\n"
        f"Query: {query.strip()}\n\n"
        f"{('Instructions: ' + instructions.strip()) if instructions else ''}"
    )

    try:
        res = await direct_engine.generate_analysis(prompt=search_prompt, model="gemini-web/flash")
        output = [f"### [Gemini Web Search Results / 即時檢索結果]\n{res.get('text', '')}"]
        if res.get("citations"):
            output.append("\n### [Citations / 參考資料連結]\n" + "\n".join(f"- {c}" for c in res["citations"]))
        return "\n".join(output)
    except Exception as e:
        return f"[Gemini Search Error]: {e}"
