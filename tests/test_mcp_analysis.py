"""
Unit tests for Gemini Analysis MCP Tools & Server.
"""

import sys
import os
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.mcp.gemini_analysis_tools import (
    analyze_code,
    ask_gemini,
    inspect_image,
    web_search,
)
from mcp_server import mcp


@pytest.mark.asyncio
async def test_analyze_code_with_local_file(tmp_path):
    test_file = tmp_path / "sample.py"
    test_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    mock_resp = {
        "text": "Code looks good and clean.",
        "thought": "Checking syntax and structure...",
        "citations": [],
        "model": "gemini-pro",
    }

    with patch("server.mcp.gemini_analysis_tools.direct_engine.generate_analysis", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_resp
        result = await analyze_code(
            files=[str(test_file)],
            instructions="Review this python file.",
            model="gemini-web/pro",
        )

        assert "### [Gemini Reasoning / 思考過程]" in result
        assert "Checking syntax and structure..." in result
        assert "### [Gemini Code Review / 代碼審查報告]" in result
        assert "Code looks good and clean." in result
        mock_gen.assert_called_once()
        prompt_arg = mock_gen.call_args[1]["prompt"]
        assert "def hello():" in prompt_arg
        assert "Review this python file." in prompt_arg


@pytest.mark.asyncio
async def test_analyze_code_with_snippet():
    mock_resp = {
        "text": "Found SQL injection vulnerability on line 2.",
        "thought": "Looking for unsanitized queries...",
        "citations": [],
        "model": "gemini-pro",
    }

    with patch("server.mcp.gemini_analysis_tools.direct_engine.generate_analysis", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_resp
        result = await analyze_code(
            code_snippet="cursor.execute('SELECT * FROM users WHERE id = ' + user_id)",
            instructions="Security audit.",
        )

        assert "SQL injection vulnerability" in result
        assert "Looking for unsanitized queries..." in result


@pytest.mark.asyncio
async def test_ask_gemini():
    mock_resp = {
        "text": "You should use an LRU cache or Redis.",
        "thought": "Considering scalability requirements...",
        "citations": ["https://redis.io"],
        "model": "gemini-pro",
    }

    with patch("server.mcp.gemini_analysis_tools.direct_engine.generate_analysis", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_resp
        result = await ask_gemini(
            prompt="How should I cache high-throughput API results?",
            model="gemini-web/pro",
        )

        assert "LRU cache or Redis" in result
        assert "Considering scalability" in result
        assert "https://redis.io" in result


@pytest.mark.asyncio
async def test_inspect_image(tmp_path):
    img_file = tmp_path / "test_ui.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    mock_resp = {
        "text": "Detected navigation bar and submit button.",
        "thought": "Analyzing layout regions...",
        "citations": [],
        "model": "gemini-flash",
    }

    with patch("server.mcp.gemini_analysis_tools.direct_engine.generate_analysis", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_resp
        result = await inspect_image(
            image_path=str(img_file),
            prompt="Identify UI components.",
        )

        assert "navigation bar" in result
        assert "Analyzing layout" in result
        mock_gen.assert_called_once()
        files_arg = mock_gen.call_args[1]["files"]
        assert len(files_arg) == 1
        assert files_arg[0].name == "image.png"


@pytest.mark.asyncio
async def test_web_search():
    mock_resp = {
        "text": "FastAPI 0.115 introduced updated dependency lifespans.",
        "thought": "Searching Google for FastAPI changelog...",
        "citations": ["https://fastapi.tiangolo.com/release-notes/"],
        "model": "gemini-flash",
    }

    with patch("server.mcp.gemini_analysis_tools.direct_engine.generate_analysis", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_resp
        result = await web_search(
            query="FastAPI 0.115 release notes",
        )

        assert "FastAPI 0.115" in result
        assert "https://fastapi.tiangolo.com/release-notes/" in result


@pytest.mark.asyncio
async def test_mcp_server_registered_tools():
    # Verify all expected analysis tools are registered in MCPServer
    tool_names = [t.name for t in await mcp.list_tools()]
    expected_tools = [
        "webchat_analyze_code",
        "webchat_ask",
        "webchat_multimodal_inspect",
        "webchat_web_search",
        "webchat_models",
        "get_webchat_status",
        "mcp_doctor",
    ]

    # Verify backward-compat aliases have been removed
    removed_tools = [
        "gemini_analyze_code",
        "gemini_ask",
        "gemini_multimodal_inspect",
        "gemini_web_search",
        "ask_gemini_web",
        "gemini_web_models",
        "get_gemini_web_status",
    ]
    for old in removed_tools:
        assert old not in tool_names, f"Compatibility alias '{old}' should have been removed."
    for exp in expected_tools:
        assert exp in tool_names, f"Expected tool '{exp}' not found in registered MCP tools: {tool_names}"

    # Verify filesystem and shell tools are excluded per user simplification requirement
    excluded_tools = [
        "mcp_read_file",
        "mcp_write_file",
        "mcp_edit_file",
        "mcp_list_dir",
        "mcp_find_files",
        "mcp_grep_search",
        "mcp_run_command",
    ]
    for exc in excluded_tools:
        assert exc not in tool_names, f"Tool '{exc}' should not be exposed in simplified MCP server."
