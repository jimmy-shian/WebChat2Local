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
    assert "CRITICAL SYSTEM DIRECTIVE - LOCAL WORKSPACE TOOL ACCESS" in prompt
    assert '<tool_call>{"name": "TOOL_NAME", "arguments": {"PARAM": "VALUE"}}</tool_call>' in prompt


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
    assert len(compiled.text) <= 45000
    assert "<system_instructions>" in compiled.text
    assert "You are a senior developer." in compiled.text
    assert "Final question: summarize the codebase." in compiled.text
    assert "已自動存入本地暫存檔案" in compiled.text or "tool result truncated" in compiled.text


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


def test_tool_call_extraction_with_parameters_and_markdown_blocks():
    # Test 'parameters' key fallback
    text1 = '<tool_call>{"name": "grep_search", "parameters": {"query": "def main"}}</tool_call>'
    tools1 = SessionManager.extract_tool_calls(text1)
    assert len(tools1) == 1
    assert tools1[0]["name"] == "grep_search"
    assert tools1[0]["arguments"]["query"] == "def main"

    # Test markdown code block format
    text2 = '```json\n{\n  "name": "execute_command",\n  "arguments": {"command": "dir"}\n}\n```'
    tools2 = SessionManager.extract_tool_calls(text2)
    assert len(tools2) == 1
    assert tools2[0]["name"] == "execute_command"
    assert tools2[0]["arguments"]["command"] == "dir"


def test_standard_coding_tools_xml_extracted_without_explicit_tool_list():
    # When available_tool_names is None, standard tools should still be recognized
    text = "<execute_command>\n<command>git status</command>\n</execute_command>"
    tools = SessionManager.extract_tool_calls(text, available_tool_names=None)
    assert len(tools) == 1
    assert tools[0]["name"] == "execute_command"
    assert tools[0]["arguments"]["command"] == "git status"


def test_prompt_compilation_with_anthropic_and_openai_tool_results():
    # Anthropic block format in user message
    messages_anthropic = [
        ChatMessage(role="user", content="Read the config file"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[{
                "id": "call_123",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "config.json"}'}
            }]
        ),
        ChatMessage(
            role="user",
            content=[
                {
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": '{"api_key": "secret", "port": 8765}'
                }
            ]
        )
    ]
    prompt_anthropic = SessionManager.compile_prompt(messages_anthropic)
    assert '<tool_result id="call_123">' in prompt_anthropic
    assert '{"api_key": "secret", "port": 8765}' in prompt_anthropic
    assert '<tool_call id="call_123">' in prompt_anthropic

    # OpenAI role: "tool" message format
    messages_openai = [
        ChatMessage(role="user", content="Check directory"),
        ChatMessage(
            role="assistant",
            content="Listing directory now",
            tool_calls=[{
                "id": "call_456",
                "type": "function",
                "function": {"name": "list_dir", "arguments": {"path": "."}}
            }]
        ),
        ChatMessage(
            role="tool",
            tool_call_id="call_456",
            name="list_dir",
            content="file1.txt\nfile2.py\nREADME.md"
        )
    ]
    prompt_openai = SessionManager.compile_prompt(messages_openai)
    assert '<tool_result name="list_dir" id="call_456">' in prompt_openai
    assert "file1.txt\nfile2.py\nREADME.md" in prompt_openai


def test_question_asking_tool_extraction():
    # 1. XML with question and options tags
    text_xml = """
    <ask_followup_question>
    <question>請問您希望先進行哪一項更新？</question>
    <options>
    <option>更新伺服器端點</option>
    <option>更新擴充功能</option>
    </options>
    </ask_followup_question>
    """
    tools_xml = SessionManager.extract_tool_calls(text_xml)
    assert len(tools_xml) == 1
    assert tools_xml[0]["name"] == "ask_followup_question"
    assert tools_xml[0]["arguments"]["question"] == "請問您希望先進行哪一項更新？"
    assert tools_xml[0]["arguments"]["options"] == ["更新伺服器端點", "更新擴充功能"]

    # 2. JSON direct parameter inside tool_call
    text_json = '<tool_call>{"question": "是否要繼續執行測試？"}</tool_call>'
    tools_json = SessionManager.extract_tool_calls(text_json)
    assert len(tools_json) == 1
    assert tools_json[0]["name"] == "ask_followup_question"
    assert tools_json[0]["arguments"]["question"] == "是否要繼續執行測試？"

    # 3. Simple text inside ask_followup_question XML
    text_simple = "<ask_followup_question>請確認您是否已登入 Google 帳號？</ask_followup_question>"
    tools_simple = SessionManager.extract_tool_calls(text_simple)
    assert len(tools_simple) == 1
    assert tools_simple[0]["name"] == "ask_followup_question"
    assert tools_simple[0]["arguments"]["question"] == "請確認您是否已登入 Google 帳號？"


def test_list_and_todo_tool_extraction():
    # 1. update_todo_list XML with JSON list
    text_todo = """
    <update_todo_list>
    [
        {"id": "1", "task": "掃描專案變更", "status": "completed"},
        {"id": "2", "task": "產生 Commit 訊息", "status": "in_progress"}
    ]
    </update_todo_list>
    """
    tools_todo = SessionManager.extract_tool_calls(text_todo)
    assert len(tools_todo) == 1
    assert tools_todo[0]["name"] == "update_todo_list"
    assert isinstance(tools_todo[0]["arguments"]["todos"], list)
    assert len(tools_todo[0]["arguments"]["todos"]) == 2

    # 2. list_files XML with path and recursive
    text_list_files = """
    <list_files>
    <path>server/bridge</path>
    <recursive>true</recursive>
    </list_files>
    """
    tools_list = SessionManager.extract_tool_calls(text_list_files)
    assert len(tools_list) == 1
    assert tools_list[0]["name"] == "list_files"
    assert tools_list[0]["arguments"]["path"] == "server/bridge"
    assert tools_list[0]["arguments"]["recursive"] is True

    # 3. list_code_definition_names XML
    text_code_def = "<list_code_definition_names><path>server/app.py</path></list_code_definition_names>"
    tools_code_def = SessionManager.extract_tool_calls(text_code_def)
    assert len(tools_code_def) == 1
    assert tools_code_def[0]["name"] == "list_code_definition_names"
    assert tools_code_def[0]["arguments"]["path"] == "server/app.py"


def test_google_specific_grounding_and_corrupted_tool_call_repair():
    # 1. Google Search prefix merged directly into "name": "..."
    text_google_search = 'Google Searchname": "execute_command", "arguments": {"command": "git status", "cwd": null}}</tool_call>'
    tools_1 = SessionManager.extract_tool_calls(text_google_search)
    assert len(tools_1) == 1
    assert tools_1[0]["name"] == "execute_command"
    assert tools_1[0]["arguments"]["command"] == "git status"

    # 2. Missing leading brace inside <tool_call>
    text_missing_brace = '<tool_call>name": "read_file", "arguments": {"path": "server/app.py"}}</tool_call>'
    tools_2 = SessionManager.extract_tool_calls(text_missing_brace)
    assert len(tools_2) == 1
    assert tools_2[0]["name"] == "read_file"
    assert tools_2[0]["arguments"]["path"] == "server/app.py"

    # 3. Python/tool_code function call syntax
    text_tool_code = """
    ```tool_code
    execute_command(command="git diff")
    ```
    """
    tools_3 = SessionManager.extract_tool_calls(text_tool_code)
    assert len(tools_3) == 1
    assert tools_3[0]["name"] == "execute_command"
    assert tools_3[0]["arguments"]["command"] == "git diff"

    # 4. ReAct Action/Action Input syntax
    text_react = """
    Action: execute_command
    Action Input: {"command": "python -m pytest"}
    """
    tools_4 = SessionManager.extract_tool_calls(text_react)
    assert len(tools_4) == 1
    assert tools_4[0]["name"] == "execute_command"
    assert tools_4[0]["arguments"]["command"] == "python -m pytest"


def test_massive_system_prompt_does_not_drop_recent_tool_results():
    # Simulate Kilo sending a 42KB system prompt + initial user query
    massive_system = "CRITICAL RULES AND SYSTEM INSTRUCTIONS\n" + ("x" * 42000) + "\nUser: 請分析 git status"
    assistant_call = "<tool_call>{\"name\": \"execute_command\", \"arguments\": {\"command\": \"git status\"}}</tool_call>"
    tool_result = "<tool_result name=\"execute_command\">\nOn branch master\nmodified: README.md\nmodified: server/app.py\n</tool_result>"

    messages = [
        ChatMessage(role="user", content=massive_system),
        ChatMessage(role="assistant", content=assistant_call),
        ChatMessage(role="user", content=tool_result),
    ]

    compiled = GeminiPromptCompiler.compile(messages)
    text = compiled.text
    # 1. Total prompt must respect Gemini Web limit
    assert len(text) <= 46500
    # 2. Crucially, the git status tool result MUST NOT be dropped!
    assert "On branch master" in text
    assert "modified: server/app.py" in text
    assert "<tool_result" in text


def test_large_tool_output_file_spillover():
    from server.bridge.prompt_compiler import spill_or_compact_tool_result, SPILLOVER_DIR
    import os

    # Simulate 111,581 chars git status + diff
    status_header = (
        "On branch master\n"
        "Changes to be committed:\n"
        "\tmodified: README.md\n"
        "\tnew file: docs/ARCHITECTURE.md\n"
        "Changes not staged for commit:\n"
        "\tmodified: server/app.py\n"
        "\tmodified: extension/content.js\n"
    )
    diff_body = "diff --git a/server/app.py b/server/app.py\n" + ("+ some changed line\n" * 5000)
    huge_output = status_header + diff_body  # > 100,000 characters
    assert len(huge_output) > 100000

    result = spill_or_compact_tool_result(huge_output, tool_name="execute_command")
    # 1. Output preview must be safe (< 8000 characters)
    assert len(result) < 8000
    # 2. Must preserve key status lines so Gemini sees the changes
    assert "On branch master" in result
    assert "modified: README.md" in result
    assert "modified: server/app.py" in result
    # 3. Must indicate spillover path
    assert "已自動存入本地暫存檔案" in result
    assert SPILLOVER_DIR in result


def test_session_continuation_detection_and_incremental_compilation():
    from server.bridge.session_manager import SessionManager

    # Turn 0: Fresh task
    turn_0 = [ChatMessage(role="user", content="請分析專案狀態")]
    assert SessionManager.is_continuation_turn(turn_0) is False

    # Turn 1: Continuation with tool call and result
    turn_1 = [
        ChatMessage(role="user", content="CRITICAL SYSTEM INSTRUCTIONS\n" + ("x" * 20000) + "\n請分析專案狀態"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[{"id": "c1", "type": "function", "function": {"name": "execute_command", "arguments": {"command": "git status"}}}]
        ),
        ChatMessage(
            role="tool",
            tool_call_id="c1",
            name="execute_command",
            content="On branch master\nmodified: README.md"
        )
    ]
    assert SessionManager.is_continuation_turn(turn_1) is True

    # When compiling for browser session, it should ONLY include the incremental tool result
    compiled = SessionManager.compile_rich_prompt(turn_1, for_browser_session=True)
    assert compiled.is_continuation is True
    # The incremental prompt should NOT include the 20,000 char turn 0 system prompt
    assert "CRITICAL SYSTEM INSTRUCTIONS" not in compiled.text
    assert len(compiled.text) < 1000
    assert "On branch master" in compiled.text
    assert "modified: README.md" in compiled.text
