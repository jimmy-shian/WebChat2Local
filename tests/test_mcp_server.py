import os
import json
import pytest
import asyncio
from pathlib import Path

# Adjust workspace root for testing
os.environ["W2L_WORKSPACE"] = os.getcwd()

from server.mcp.mcp_server import (
    mcp, resolve_path, get_workspace_root, _compute_revision,
    run_command, create_file, read_file, edit_file, delete_file,
    list_directory, grep_search
)

def test_tools_registered():
    assert mcp.name == "webchat2local-studio"

@pytest.mark.asyncio
async def test_run_command():
    result_str = await run_command("echo hello")
    result = json.loads(result_str)
    assert result["exit_code"] == 0
    assert "hello" in result["stdout"]

def test_file_roundtrip():
    test_file = "test_roundtrip.txt"
    test_content = "initial content"
    
    # Cleanup before test
    p = resolve_path(test_file)
    if p.exists():
        p.unlink()
    
    # 1. create_file
    res_create = json.loads(create_file(test_file, test_content))
    assert res_create["status"] == "success"
    rev1 = res_create["revision"]
    
    # 2. read_file
    res_read = read_file(test_file)
    assert "initial content" in res_read
    
    # 3. edit_file
    edits = [{"old_text": "initial", "new_text": "updated"}]
    res_edit = json.loads(edit_file(test_file, rev1, edits))
    assert res_edit.get("status") == "success", res_edit
    rev2 = res_edit["revision"]
    
    # Verify edit
    res_read2 = read_file(test_file)
    assert "updated content" in res_read2
    
    # Clean up
    delete_file(test_file, rev2)
    assert not p.exists()

def test_workspace_security():
    # path traversal attempt should fail
    with pytest.raises(ValueError, match="Path traversal attempt detected"):
        resolve_path("../outside_workspace.txt")
        
    with pytest.raises(ValueError, match="UNC paths are not allowed"):
        resolve_path("\\\\server\\share\\file.txt")
