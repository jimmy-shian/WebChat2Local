"""
Unit tests for Stream Adapters, Session Manager, and Prompt Compiler.
"""

import sys
import json
import pytest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.bridge.ws_hub import TurnEvent
from server.bridge.stream_adapter import (
    stream_openai_completions,
    stream_responses_api,
    collect_complete_response,
)
from server.bridge.session_manager import SessionManager
from server.bridge.prompt_compiler import GeminiPromptCompiler
from server.protocol import ChatMessage


@pytest.mark.asyncio
async def test_openai_stream_with_thinking():
    async def mock_events():
        yield TurnEvent(event_type="delta", delta="", thought_delta="Thinking about python code...")
        yield TurnEvent(event_type="delta", delta="def add(a, b):\n", thought_delta="")
        yield TurnEvent(event_type="delta", delta="    return a + b", thought_delta="")
        yield TurnEvent(event_type="done", text="def add(a, b):\n    return a + b", thought="Thinking about python code...")

    chunks = []
    async for chunk in stream_openai_completions(mock_events(), model="gemini-web/pro"):
        chunks.append(chunk)

    full_stream = "".join(chunks)
    assert "data: " in full_stream
    assert "data: [DONE]" in full_stream
    assert "Thinking about python code..." in full_stream
    assert "def add(a, b):" in full_stream


@pytest.mark.asyncio
async def test_openai_stream_converts_tool_xml_to_structured_tool_call():
    async def mock_events():
        yield TurnEvent(
            event_type="delta",
            delta='I will inspect it.\n<tool_call>{"name":"read_file","arguments":{"path":"test.py"}}',
        )
        yield TurnEvent(
            event_type="done",
            text='I will inspect it.\n<tool_call>{"name":"read_file","arguments":{"path":"test.py"}}</tool_call>',
        )

    chunks = []
    async for chunk in stream_openai_completions(
        mock_events(),
        model="gemini-web/pro",
        available_tool_names=["read_file"],
    ):
        chunks.append(chunk)

    full_stream = "".join(chunks)
    assert '"tool_calls"' in full_stream
    assert '"name": "read_file"' in full_stream
    assert '"finish_reason": "tool_calls"' in full_stream
    assert "<tool_call>" not in full_stream


@pytest.mark.asyncio
async def test_responses_api_stream():
    async def mock_events():
        yield TurnEvent(event_type="delta", delta="Hello from Gemini", thought_delta="Thinking...")
        yield TurnEvent(event_type="done", text="Hello from Gemini", thought="Thinking...")

    events = []
    async for item in stream_responses_api(mock_events(), model="gemini-web/pro"):
        events.append(item)

    full_stream = "".join(events)
    assert "event: response.created" in full_stream
    assert "event: response.reasoning.delta" in full_stream
    assert "event: response.text.delta" in full_stream
    assert "event: response.completed" in full_stream


@pytest.mark.asyncio
async def test_collect_complete_response_with_tools():
    tool_text = "Let me read the file.\n<tool_call>{\"name\": \"read_file\", \"arguments\": {\"path\": \"test.py\"}}</tool_call>"
    async def mock_events():
        yield TurnEvent(event_type="done", text=tool_text, thought="Analyzing request")

    resp = await collect_complete_response(mock_events(), model="gemini-web/pro")
    assert resp.model == "gemini-web/pro"
    choice = resp.choices[0]
    assert choice.message.role == "assistant"
    assert choice.message.reasoning_content == "Analyzing request"
    assert choice.message.tool_calls is not None
    assert len(choice.message.tool_calls) == 1
    assert choice.message.tool_calls[0].function.name == "read_file"


def test_session_manager_prompt_compilation():
    messages = [
        ChatMessage(role="system", content="You are a helpful coding assistant."),
        ChatMessage(role="user", content="Show me project files."),
    ]
    prompt = SessionManager.compile_prompt(messages)
    assert "<system_instructions>" in prompt
    assert "You are a helpful coding assistant." in prompt
    assert "<user>\nShow me project files.\n</user>" in prompt


def test_tool_call_extraction():
    text = (
        "I will now list the directory.\n"
        "<tool_call>{\"name\": \"list_dir\", \"arguments\": {\"path\": \".\"}}</tool_call>\n"
        "And then create a file."
    )
    tools = SessionManager.extract_tool_calls(text)
    assert len(tools) == 1
    assert tools[0]["name"] == "list_dir"
    assert tools[0]["arguments"] == {"path": "."}


def test_tool_call_extraction_from_exact_gemini_web_payload():
    text = '<tool_call>{"name":"execute_command","arguments":{"command":"git --no-pager status --short && git --no-pager log -n 5 --oneline","cwd":null}}</tool_call>'
    tools = SessionManager.extract_tool_calls(text, ["execute_command"])
    assert len(tools) == 1
    assert tools[0]["name"] == "execute_command"
    assert tools[0]["arguments"]["command"].startswith("git --no-pager status")


def test_tool_call_extraction_accepts_cline_xml_dialect():
    tools = SessionManager.extract_tool_calls(
        "<read_file><path>index.html</path></read_file>",
        ["read_file"],
    )
    assert len(tools) == 1
    assert tools[0]["name"] == "read_file"
    assert tools[0]["arguments"] == {"path": "index.html"}


def test_prompt_compiler_generates_tool_protocol_instruction():
    prompt = SessionManager.compile_prompt(
        [ChatMessage(role="user", content="Read test.py")],
        tools=[{
            "type": "function",
            "function": {
                "name": "read_file",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
            },
        }],
    )
    assert "host client owns and executes tools" in prompt
    assert '<tool_call>{"name":"TOOL_NAME","arguments":{}}</tool_call>' in prompt


def test_prompt_compiler_compacts_oversized_prompts():
    # Build an oversized conversation (100k+ chars) with massive tool results
    huge_file_content = "X" * 30000
    huge_dir_content = "Y" * 40000
    messages = [
        ChatMessage(role="system", content="You are a senior developer."),
        ChatMessage(role="user", content="Start task: analyze repository."),
        ChatMessage(role="assistant", content="I will read file.", reasoning_content="Thinking about file structure " * 200),
        ChatMessage(role="tool", content=huge_file_content, name="read_file"),
        ChatMessage(role="assistant", content="Now I will check directory."),
        ChatMessage(role="tool", content=huge_dir_content, name="list_dir"),
        ChatMessage(role="user", content="Final question: summarize the codebase."),
    ]
    compiled = GeminiPromptCompiler.compile(messages)
    assert len(compiled.text) <= 16000
    assert "<system_instructions>" in compiled.text
    assert "You are a senior developer." in compiled.text
    assert "Final question: summarize the codebase." in compiled.text
    assert "tool result truncated" in compiled.text


@pytest.mark.asyncio
async def test_stream_with_markdown_urls_and_cjk():
    sample_text = (
        "我們將根據你的需求，進行兩個部分的整理規劃與重構：\n\n"
        "### 一、 Markdown 說明文件整合方案\n"
        "1. **使用者指南與快速上手手冊**\n"
        "   - **快速啟動**：一鍵啟動腳本與儀表板存取 (`[http://127.0.0.1:8765](http://127.0.0.1:8765)`)。\n"
        "   - 支援模型對照表：DeepSeek、ChatGPT、Gemini。"
    )

    async def mock_events():
        yield TurnEvent(event_type="delta", delta=sample_text[:50])
        yield TurnEvent(event_type="delta", delta=sample_text[50:120])
        yield TurnEvent(event_type="delta", delta=sample_text[120:])
        yield TurnEvent(event_type="done", text=sample_text)

    chunks = []
    async for chunk in stream_openai_completions(mock_events(), model="gemini-web/pro"):
        chunks.append(chunk)

    full_stream = "".join(chunks)
    assert "http://127.0.0.1:8765" in full_stream
    assert "支援模型對照表" in full_stream
    assert "data: [DONE]" in full_stream

    # Also test non-streaming collector
    resp = await collect_complete_response(mock_events(), model="gemini-web/pro")
    assert resp.choices[0].message.content == sample_text


def test_extract_tool_call_with_nested_code_and_tool_call_strings():
    complex_payload = (
        '<tool_call>{"name":"write_to_file","arguments":{'
        '"path":"tests/test_suite.py",'
        '"content":"import pytest\\n\\ndef test_inner():\\n    xml = \\"<tool_call>{\\\\\\"name\\\\\\": \\\\\\"read_file\\\\\\"} </tool_call>\\"\\n    assert True\\n"'
        '}}</tool_call>'
    )
    tools = SessionManager.extract_tool_calls(complex_payload, ["write_to_file"])
    assert len(tools) == 1
    assert tools[0]["name"] == "write_to_file"
    assert tools[0]["arguments"]["path"] == "tests/test_suite.py"
    assert "test_inner" in tools[0]["arguments"]["content"]
    assert "<tool_call>" in tools[0]["arguments"]["content"]
