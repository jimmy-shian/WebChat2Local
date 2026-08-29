import os
import shutil
import tempfile
import pytest

from server.tools.edit_engine import (
    read_file,
    edit_file,
    apply_proposal,
    create_file,
    delete_file,
    list_directory,
    grep_search
)
from server.tools.workspace_security import WorkspaceSecurityError

@pytest.fixture
def workspace():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

def test_full_edit_lifecycle(workspace):
    file_path = "hello.py"
    # 1. create_file
    create_file(workspace, file_path, "def hello():\n    print('hello')\n")
    
    # 2. read_file -> get revision
    file_info = read_file(workspace, file_path)
    revision = file_info["revision"]
    
    # 3. edit_file
    edits = [{"old_text": "def hello():", "new_text": "def hello(name: str):"}]
    proposal = edit_file(workspace, file_path, revision, edits)
    
    # 4. Verify proposal
    assert proposal["success"] is True
    assert "def hello(name: str):" in proposal["diff"]
    assert "proposal_id" in proposal
    
    # 5. apply_proposal
    result = apply_proposal(workspace, proposal)
    assert result["success"] is True
    
    # 6. read_file verify content
    new_info = read_file(workspace, file_path)
    assert "def hello(name: str):" in new_info["content"]
    
    # 7. verify new revision differs from original
    assert new_info["revision"] != revision

def test_stale_file_rejection(workspace):
    file_path = "config.json"
    create_file(workspace, file_path, '{"port": 8080}')
    
    file_info = read_file(workspace, file_path)
    revision = file_info["revision"]
    
    # manually modify
    abs_path = os.path.join(workspace, file_path)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write('{"port": 9090}')
        
    edits = [{"old_text": "8080", "new_text": "3000"}]
    proposal = edit_file(workspace, file_path, revision, edits)
    
    assert proposal["success"] is False
    assert proposal["error"] == "STALE_FILE"

def test_stale_proposal_rejection(workspace):
    file_path = "app.py"
    create_file(workspace, file_path, "x = 1\ny = 2\n")
    
    file_info = read_file(workspace, file_path)
    revision = file_info["revision"]
    
    edits = [{"old_text": "x = 1", "new_text": "x = 10"}]
    proposal = edit_file(workspace, file_path, revision, edits)
    assert proposal["success"] is True
    
    # manually modify before applying
    abs_path = os.path.join(workspace, file_path)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write("x = 1\ny = 3\n")
        
    result = apply_proposal(workspace, proposal)
    assert result["success"] is False
    assert result["error"] == "STALE_FILE"

def test_ambiguous_match_rejection(workspace):
    file_path = "dup.txt"
    create_file(workspace, file_path, "foo\nbar\nfoo\nbaz\n")
    
    file_info = read_file(workspace, file_path)
    revision = file_info["revision"]
    
    edits = [{"old_text": "foo", "new_text": "qux"}]
    proposal = edit_file(workspace, file_path, revision, edits)
    
    assert proposal["success"] is False
    assert proposal["error"] == "AMBIGUOUS_MATCH"

def test_edit_mismatch_with_suggestion(workspace):
    file_path = "crlf.txt"
    create_file(workspace, file_path, "line1\r\nline2\r\n")
    
    file_info = read_file(workspace, file_path)
    revision = file_info["revision"]
    
    edits = [{"old_text": "line1\nline2", "new_text": "changed"}]
    proposal = edit_file(workspace, file_path, revision, edits)
    
    assert proposal["success"] is False
    assert proposal["error"] == "EDIT_MISMATCH"
    assert proposal.get("suggested_match") is not None

def test_create_delete_lifecycle(workspace):
    file_path = "temp.txt"
    create_file(workspace, file_path, "temporary")
    
    file_info = read_file(workspace, file_path)
    revision = file_info["revision"]
    
    result = delete_file(workspace, file_path, revision)
    assert result["success"] is True
    
    abs_path = os.path.join(workspace, file_path)
    assert not os.path.exists(abs_path)
    
    # should succeed again
    result = create_file(workspace, file_path, "temporary")
    assert result["success"] is True

def test_delete_stale_rejection(workspace):
    file_path = "del.txt"
    create_file(workspace, file_path, "original")
    
    file_info = read_file(workspace, file_path)
    revision = file_info["revision"]
    
    abs_path = os.path.join(workspace, file_path)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write("modified")
        
    result = delete_file(workspace, file_path, revision)
    assert result["success"] is False
    assert result["error"] == "STALE_FILE"

def test_workspace_security_in_transaction(workspace):
    with pytest.raises(WorkspaceSecurityError):
        read_file(workspace, "../../../etc/passwd")
        
    with pytest.raises(WorkspaceSecurityError):
        create_file(workspace, "..\\..\\escape.txt", "bad")
        
    with pytest.raises(WorkspaceSecurityError):
        edit_file(workspace, "\\\\server\\share\\file.txt", "rev", [])

def test_list_and_grep(workspace):
    os.makedirs(os.path.join(workspace, "src"), exist_ok=True)
    create_file(workspace, "src/main.py", "import os\n")
    create_file(workspace, "src/utils.py", "import sys\n")
    create_file(workspace, ".env", "SECRET=123")
    
    src_res = list_directory(workspace, "src")
    src_files = [f["name"] for f in src_res["entries"]]
    assert "main.py" in src_files
    assert "utils.py" in src_files
    
    root_res = list_directory(workspace, ".")
    root_files = [f["name"] for f in root_res["entries"]]
    assert ".env" not in root_files
    
    grep_res = grep_search(workspace, "import", "src")
    matches = [m["path"] for m in grep_res["matches"]]
    assert any("main.py" in m for m in matches)
    assert any("utils.py" in m for m in matches)

def test_multi_edit_transaction(workspace):
    file_path = "multi.py"
    create_file(workspace, file_path, "a = 1\nb = 2\nc = 3\n")
    
    file_info = read_file(workspace, file_path)
    revision = file_info["revision"]
    
    edits = [
        {"old_text": "a = 1", "new_text": "a = 10"},
        {"old_text": "c = 3", "new_text": "c = 30"}
    ]
    proposal = edit_file(workspace, file_path, revision, edits)
    
    assert proposal["success"] is True
    assert "a = 10" in proposal["diff"]
    assert "c = 30" in proposal["diff"]
    
    apply_result = apply_proposal(workspace, proposal)
    assert apply_result["success"] is True
    
    final_info = read_file(workspace, file_path)
    assert final_info["content"] == "a = 10\nb = 2\nc = 30\n"
