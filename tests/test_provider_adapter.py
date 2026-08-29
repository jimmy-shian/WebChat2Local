import pytest
from server.providers.provider_adapter import format_tool_prompt, format_messages_for_web, parse_tool_response

def test_format_tool_prompt():
    tools = [{"name": "read_file", "parameters": {"properties": {"path": {}}}}]
    prompt = format_tool_prompt(tools)
    assert "read_file" in prompt
    assert '{"tool": "read_file", "arguments": {"path": "..."}}' in prompt

def test_parse_tool_response_clean_json():
    text = '{"tool": "read_file", "arguments": {"path": "test.txt"}}'
    tools = ["read_file"]
    content, calls, reason = parse_tool_response(text, tools)
    assert reason == "tool_calls"
    assert calls[0]["function"]["name"] == "read_file"

def test_parse_tool_response_markdown_json():
    text = '```json\n{"tool": "read_file", "arguments": {"path": "test.txt"}}\n```'
    tools = ["read_file"]
    content, calls, reason = parse_tool_response(text, tools)
    assert reason == "tool_calls"
    assert calls[0]["function"]["name"] == "read_file"

def test_parse_tool_response_surrounding_text():
    text = 'Here is the tool call: {"tool": "read_file", "arguments": {"path": "test.txt"}} and some more text.'
    tools = ["read_file"]
    content, calls, reason = parse_tool_response(text, tools)
    assert reason == "tool_calls"
    assert calls[0]["function"]["name"] == "read_file"

def test_parse_tool_response_synthesize_completion():
    text = 'Just some text'
    tools = ["attempt_completion", "read_file"]
    content, calls, reason = parse_tool_response(text, tools)
    assert reason == "tool_calls"
    assert calls[0]["function"]["name"] == "attempt_completion"
    assert 'Just some text' in calls[0]["function"]["arguments"]

def test_parse_tool_response_no_tools():
    text = 'Just some text'
    content, calls, reason = parse_tool_response(text, [])
    assert reason == "stop"
    assert calls is None

def test_parse_tool_response_rejects_unknown():
    text = '{"tool": "unknown_tool", "arguments": {}}'
    tools = ["read_file"]
    content, calls, reason = parse_tool_response(text, tools)
    assert reason == "stop"
    assert calls is None

def test_format_messages_for_web_filters_bloated():
    messages = [
        {"role": "system", "content": "You are Cline. This is a massive prompt." * 100},
        {"role": "user", "content": "Hello"}
    ]
    formatted = format_messages_for_web(messages, [])
    assert "You are Cline" not in formatted
    assert "Hello" in formatted

def test_format_messages_for_web_strips_environment():
    messages = [
        {"role": "user", "content": "<environment_details>Env stuff</environment_details> My question"}
    ]
    formatted = format_messages_for_web(messages, [])
    assert "Env stuff" not in formatted
    assert "My question" in formatted
