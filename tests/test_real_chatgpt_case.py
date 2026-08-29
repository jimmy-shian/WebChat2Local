import json
import pytest
import asyncio
import os
import shutil
import tempfile
from server.providers.provider_adapter import parse_tool_response
from server.agent.tool_executor import ToolExecutor

def test_chatgpt_windows_path_parsing():
    raw_text = r'{"tool":"create_file","arguments":{"path":"C:\Users\Administrator\Desktop\html_test\WebChat2Local\New.txt","content":"Hello World"}}'
    
    out_text, tool_calls, finish_reason = parse_tool_response(raw_text, ["create_file", "edit_file", "read_file"])
    
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "create_file"
    
    args = json.loads(tool_calls[0]["function"]["arguments"])
    assert "path" in args
    assert "content" in args
    assert args["content"] == "Hello World"

@pytest.mark.asyncio
async def test_tool_executor_normalization():
    tmp_dir = tempfile.mkdtemp()
    try:
        executor = ToolExecutor(tmp_dir)
        args = {"path": os.path.join(tmp_dir, "New.txt"), "content": "Hello World"}
        res = await executor.execute_tool("create_file", args)
        assert res.get("success") is True
        
        file_path = os.path.join(tmp_dir, "New.txt")
        assert os.path.exists(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            assert f.read() == "Hello World"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
