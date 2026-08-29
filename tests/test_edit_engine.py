import os
import pytest
import shutil
from server.tools.workspace_security import WorkspaceSecurityPolicy, WorkspaceSecurityError
from server.tools.edit_engine import (
    read_file, edit_file, apply_proposal, create_file, delete_file, list_directory, grep_search, compute_hash
)

@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    
    # Create test files
    with open(ws / "test.txt", "wb") as f:
        f.write(b"Hello\nWorld\n")
    with open(ws / ".env", "wb") as f:
        f.write(b"SECRET=123")
    
    (ws / "nested").mkdir()
    with open(ws / "nested" / "file.py", "wb") as f:
        f.write(b"print('Hello')")
    
    return str(ws)

def test_workspace_security_policy(workspace):
    policy = WorkspaceSecurityPolicy(workspace)
    
    # Valid
    policy.validate_path("test.txt")
    policy.validate_path("nested/file.py")
    
    # Invalid: absolute
    with pytest.raises(WorkspaceSecurityError):
        policy.validate_path(os.path.abspath("test.txt"))
        
    # Invalid: traversal
    with pytest.raises(WorkspaceSecurityError):
        policy.validate_path("../outside.txt")
        
    # Ignore patterns
    assert policy.is_ignored("node_modules/pkg/index.js")
    assert policy.is_ignored(".env")
    assert policy.is_ignored(".env.local")
    assert policy.is_ignored("key.pem")
    assert not policy.is_ignored("test.txt")

def test_read_file(workspace):
    res = read_file(workspace, "test.txt")
    assert res["path"] == "test.txt"
    assert res["content"] == "Hello\nWorld\n"
    assert res["revision"].startswith("sha256:")

def test_edit_file_success(workspace):
    res_read = read_file(workspace, "test.txt")
    res_edit = edit_file(workspace, "test.txt", res_read["revision"], [
        {"old_text": "World", "new_text": "Universe"}
    ])
    
    assert res_edit["success"]
    assert res_edit["new_content"] == "Hello\nUniverse\n"
    assert res_edit["base_revision"] == res_read["revision"]
    assert res_edit["new_revision"] != res_read["revision"]
    assert "diff" in res_edit
    assert "proposal_id" in res_edit

def test_edit_file_stale(workspace):
    res_read = read_file(workspace, "test.txt")
    
    # Modify file behind the scenes
    with open(os.path.join(workspace, "test.txt"), "wb") as f:
        f.write(b"Modified\n")
        
    res_edit = edit_file(workspace, "test.txt", res_read["revision"], [
        {"old_text": "World", "new_text": "Universe"}
    ])
    
    assert not res_edit["success"]
    assert res_edit["error"] == "STALE_FILE"

def test_edit_file_mismatch(workspace):
    res_read = read_file(workspace, "test.txt")
    res_edit = edit_file(workspace, "test.txt", res_read["revision"], [
        {"old_text": "Earth", "new_text": "Universe"}
    ])
    
    assert not res_edit["success"]
    assert res_edit["error"] == "EDIT_MISMATCH"

def test_edit_file_ambiguous(workspace):
    res_read = read_file(workspace, "test.txt")
    
    # Write ambiguous content
    with open(os.path.join(workspace, "test.txt"), "wb") as f:
        f.write(b"Hello\nHello\n")
        
    res_read2 = read_file(workspace, "test.txt")
    res_edit = edit_file(workspace, "test.txt", res_read2["revision"], [
        {"old_text": "Hello\n", "new_text": "Hi\n"}
    ])
    
    assert not res_edit["success"]
    assert res_edit["error"] == "AMBIGUOUS_MATCH"

def test_edit_file_crlf_mismatch(workspace):
    # Setup CRLF file
    with open(os.path.join(workspace, "crlf.txt"), "wb") as f:
        f.write(b"Hello\r\nWorld\r\n")
        
    res_read = read_file(workspace, "crlf.txt")
    res_edit = edit_file(workspace, "crlf.txt", res_read["revision"], [
        {"old_text": "Hello\nWorld\n", "new_text": "Hi\nWorld\n"}
    ])
    
    assert not res_edit["success"]
    assert res_edit["error"] == "EDIT_MISMATCH"
    assert res_edit["suggested_match"] is not None

def test_apply_proposal_success(workspace):
    res_read = read_file(workspace, "test.txt")
    res_edit = edit_file(workspace, "test.txt", res_read["revision"], [
        {"old_text": "World", "new_text": "Universe"}
    ])
    
    res_apply = apply_proposal(workspace, res_edit)
    assert res_apply["success"]
    
    res_read2 = read_file(workspace, "test.txt")
    assert res_read2["content"] == "Hello\nUniverse\n"

def test_apply_proposal_stale(workspace):
    res_read = read_file(workspace, "test.txt")
    res_edit = edit_file(workspace, "test.txt", res_read["revision"], [
        {"old_text": "World", "new_text": "Universe"}
    ])
    
    # Modify behind the scenes
    with open(os.path.join(workspace, "test.txt"), "wb") as f:
        f.write(b"Modified\n")
        
    res_apply = apply_proposal(workspace, res_edit)
    assert not res_apply["success"]
    assert res_apply["error"] == "STALE_FILE"

def test_create_file(workspace):
    res = create_file(workspace, "new.txt", "Content")
    assert res["success"]
    assert os.path.exists(os.path.join(workspace, "new.txt"))
    
    # Exists
    res2 = create_file(workspace, "new.txt", "Content2")
    assert not res2["success"]
    assert res2["error"] == "FILE_EXISTS"

def test_delete_file(workspace):
    res_read = read_file(workspace, "test.txt")
    
    # Wrong revision
    res_del_fail = delete_file(workspace, "test.txt", "sha256:wrong")
    assert not res_del_fail["success"]
    assert res_del_fail["error"] == "STALE_FILE"
    
    # Success
    res_del = delete_file(workspace, "test.txt", res_read["revision"])
    assert res_del["success"]
    assert not os.path.exists(os.path.join(workspace, "test.txt"))

def test_list_directory(workspace):
    res = list_directory(workspace)
    names = [e["name"] for e in res["entries"]]
    assert "test.txt" in names
    assert "nested" in names
    assert ".env" not in names # Ignored

def test_grep_search(workspace):
    res = grep_search(workspace, "Hello")
    assert len(res["matches"]) == 2
    paths = [m["path"].replace("\\", "/") for m in res["matches"]]
    assert "test.txt" in paths
    assert "nested/file.py" in paths
    
    res2 = grep_search(workspace, "SECRET")
    assert len(res2["matches"]) == 0 # Ignored .env
