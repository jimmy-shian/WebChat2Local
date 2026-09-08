"""
Unified Test Suite for MCP Server, Tools, and Protocol Handshake.
Consolidates MCP initialize handshake, filesystem tools, search tools, and shell tools.
"""

import os
import sys
import json
import pytest
import subprocess
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["W2L_WORKSPACE"] = os.getcwd()

PYTHON_EXE = sys.executable
MCP_SCRIPT = str(PROJECT_ROOT / "mcp_server.py")

from mcp_server import mcp, webchat_models
from server.mcp.tools_filesystem import (
    read_file, write_file, edit_file, delete_file, list_dir, find_files, _resolve_safe_path
)
from server.mcp.tools_search import grep_search
from server.mcp.tools_shell import run_command
from server.mcp.tools_system import get_workspace_status, doctor


# ----------------------------------------------------------------------------
# 1. MCP Server & Catalog Tests
# ----------------------------------------------------------------------------

def test_mcp_server_name():
    assert mcp.name == "gemini-web-bridge"


def test_webchat_models_catalog():
    models_json = webchat_models()
    data = json.loads(models_json)
    assert "models" in data
    assert any(m["id"] == "gemini-web/pro" for m in data["models"])


# ----------------------------------------------------------------------------
# 2. Stdio JSON-RPC 2.0 Handshake
# ----------------------------------------------------------------------------

def test_mcp_server_initialize_and_tools():
    proc = subprocess.Popen(
        [PYTHON_EXE, MCP_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=str(Path.home())  # Run from outside workspace to test robustness
    )

    try:
        # 1. Send initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "Antigravity-Test",
                    "version": "1.0.0"
                }
            }
        }
        proc.stdin.write(json.dumps(init_request) + "\n")
        proc.stdin.flush()

        resp_line = proc.stdout.readline()
        assert resp_line, "MCP server did not return any output on initialize"
        resp_data = json.loads(resp_line.strip())
        assert resp_data.get("id") == 1
        assert "result" in resp_data
        assert resp_data["result"]["serverInfo"]["name"] == "gemini-web-bridge"

        # 2. Send initialized notification
        init_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        proc.stdin.write(json.dumps(init_notif) + "\n")
        proc.stdin.flush()

        # 3. Send tools/list request
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        proc.stdin.write(json.dumps(tools_request) + "\n")
        proc.stdin.flush()

        tools_resp_line = proc.stdout.readline()
        assert tools_resp_line, "MCP server did not return tools list"
        tools_data = json.loads(tools_resp_line.strip())
        assert tools_data.get("id") == 2
        tool_names = [t["name"] for t in tools_data["result"]["tools"]]
        assert "webchat_ask" in tool_names
        assert "get_webchat_status" in tool_names
        assert "webchat_models" in tool_names

    finally:
        proc.kill()
        proc.wait()


# ----------------------------------------------------------------------------
# 3. Tool Execution & Security Tests
# ----------------------------------------------------------------------------

@pytest.fixture
def temp_workspace(tmp_path, monkeypatch):
    """Sets a temporary directory as the active workspace root."""
    monkeypatch.setenv("W2L_WORKSPACE", str(tmp_path))
    return tmp_path


def test_filesystem_crud(temp_workspace):
    # 1. Write file
    res_write = write_file("test.txt", "Hello World\nLine 2\nLine 3", overwrite=True)
    assert res_write["status"] == "success"
    assert (temp_workspace / "test.txt").exists()

    # 2. Read file
    res_read = read_file("test.txt")
    assert res_read["status"] == "success"
    assert res_read["content"] == "Hello World\nLine 2\nLine 3"
    assert res_read["total_lines"] == 3

    # 3. Read file with line range
    res_range = read_file("test.txt", start_line=2, end_line=2)
    assert res_range["status"] == "success"
    assert res_range["content"] == "Line 2\n"

    # 4. Edit file
    res_edit = edit_file("test.txt", search_target="Line 2", replacement="Line Modified")
    assert res_edit["status"] == "success"
    assert (temp_workspace / "test.txt").read_text(encoding="utf-8") == "Hello World\nLine Modified\nLine 3"

    # 5. List dir
    res_list = list_dir(".")
    assert res_list["status"] == "success"
    assert res_list["total_items"] == 1
    assert res_list["items"][0]["name"] == "test.txt"

    # 6. Delete file
    res_del = delete_file("test.txt")
    assert res_del["status"] == "success"
    assert not (temp_workspace / "test.txt").exists()


def test_workspace_security():
    with pytest.raises(ValueError, match="Access denied"):
        _resolve_safe_path("../outside_workspace.txt")
        
    with pytest.raises(ValueError, match="UNC network paths are not allowed"):
        _resolve_safe_path("\\\\server\\share\\file.txt")


def test_search_and_shell_tools(temp_workspace):
    (temp_workspace / "src").mkdir()
    (temp_workspace / "src" / "main.py").write_text("def hello():\n    return 'Gemini Bridge'", encoding="utf-8")
    
    # 1. find_files
    res_find = find_files(pattern="*.py", search_dir=".")
    assert res_find["status"] == "success"
    assert res_find["total_matches"] == 1
    assert res_find["matches"][0]["name"] == "main.py"

    # 2. grep_search
    res_grep = grep_search(query="Gemini Bridge", search_path=".")
    assert res_grep["status"] == "success"
    assert res_grep["total_matches"] == 1
    assert "main.py" in res_grep["matches"][0]["file"]

    # 3. run_command
    res_sh = run_command("echo hello")
    assert res_sh["exit_code"] == 0
    assert "hello" in res_sh["stdout"]


def test_system_status_and_doctor(temp_workspace):
    res_status = get_workspace_status()
    assert res_status["status"] == "healthy"
    assert "python_version" in res_status

    res_doc = doctor()
    assert res_doc["status"] == "healthy"
    assert len(res_doc["checks"]) >= 2
