import os
import hashlib
import uuid
import difflib
import re
from typing import List, Dict, Any, Optional
from .workspace_security import WorkspaceSecurityPolicy, WorkspaceSecurityError

def compute_hash(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()

def read_file(workspace_root: str, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> dict:
    policy = WorkspaceSecurityPolicy(workspace_root)
    full_path = policy.validate_path(path)
    
    with open(full_path, "rb") as f:
        content_bytes = f.read()
    
    content_str = content_bytes.decode("utf-8")
    revision = compute_hash(content_bytes)
    
    if start_line is not None or end_line is not None:
        lines = content_str.splitlines(keepends=True)
        total_lines = len(lines)
        s = max(1, start_line) if start_line is not None else 1
        e = min(total_lines, end_line) if end_line is not None else total_lines
        sliced_lines = lines[s - 1: e]
        sliced_content = "".join(sliced_lines)
        return {
            "path": path,
            "revision": revision,
            "content": sliced_content,
            "start_line": s,
            "end_line": e,
            "total_lines": total_lines
        }

    return {
        "path": path,
        "revision": revision,
        "content": content_str
    }

def edit_file(workspace_root: str, path: str, revision: str, edits: List[Dict[str, str]]) -> dict:
    policy = WorkspaceSecurityPolicy(workspace_root)
    full_path = policy.validate_path(path)
    
    with open(full_path, "rb") as f:
        content_bytes = f.read()
        
    current_hash = compute_hash(content_bytes)
    if current_hash != revision:
        return {
            "success": False, 
            "error": "STALE_FILE", 
            "message": f"File has been modified since read. Current revision: {current_hash}"
        }
        
    content_str = content_bytes.decode("utf-8")
    original_lines = content_str.splitlines(keepends=True)
    
    new_content_str = content_str
    
    for edit in edits:
        old_text = edit["old_text"]
        new_text = edit["new_text"]
        
        count = new_content_str.count(old_text)
        if count == 0:
            # Try LF/CRLF
            old_norm = old_text.replace("\r\n", "\n")
            curr_norm = new_content_str.replace("\r\n", "\n")
            if curr_norm.count(old_norm) > 0:
                return {
                    "success": False,
                    "error": "EDIT_MISMATCH",
                    "message": "old_text not found exactly, but matches ignoring line endings.",
                    "suggested_match": old_norm
                }
            return {
                "success": False,
                "error": "EDIT_MISMATCH",
                "message": "old_text not found in file.",
                "suggested_match": None
            }
        elif count > 1:
            return {
                "success": False,
                "error": "AMBIGUOUS_MATCH",
                "message": f"old_text matches {count} locations. Add more surrounding context."
            }
            
        new_content_str = new_content_str.replace(old_text, new_text)

    new_content_bytes = new_content_str.encode("utf-8")
    new_hash = compute_hash(new_content_bytes)
    
    new_lines = new_content_str.splitlines(keepends=True)
    diff = "".join(difflib.unified_diff(original_lines, new_lines, fromfile=path, tofile=path))
    
    return {
        "success": True,
        "proposal_id": str(uuid.uuid4()),
        "path": path,
        "base_revision": revision,
        "new_revision": new_hash,
        "diff": diff,
        "new_content": new_content_str
    }

def apply_proposal(workspace_root: str, proposal: dict) -> dict:
    path = proposal["path"]
    base_revision = proposal["base_revision"]
    new_content = proposal["new_content"]
    
    policy = WorkspaceSecurityPolicy(workspace_root)
    full_path = policy.validate_path(path)
    
    with open(full_path, "rb") as f:
        current_hash = compute_hash(f.read())
        
    if current_hash != base_revision:
        return {"success": False, "error": "STALE_FILE"}
        
    with open(full_path, "wb") as f:
        f.write(new_content.encode("utf-8"))
        
    return {
        "success": True, 
        "path": path, 
        "revision": proposal["new_revision"]
    }

def create_file(workspace_root: str, path: str, content: str) -> dict:
    policy = WorkspaceSecurityPolicy(workspace_root)
    full_path = policy.validate_path(path)
    
    if os.path.exists(full_path):
        return {"success": False, "error": "FILE_EXISTS"}
        
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    content_bytes = content.encode("utf-8")
    with open(full_path, "wb") as f:
        f.write(content_bytes)
        
    return {
        "success": True,
        "path": path,
        "revision": compute_hash(content_bytes)
    }

def delete_file(workspace_root: str, path: str, revision: str) -> dict:
    policy = WorkspaceSecurityPolicy(workspace_root)
    full_path = policy.validate_path(path)
    
    with open(full_path, "rb") as f:
        current_hash = compute_hash(f.read())
        
    if current_hash != revision:
        return {"success": False, "error": "STALE_FILE"}
        
    os.remove(full_path)
    return {"success": True, "path": path}

def list_directory(workspace_root: str, path: str = ".") -> dict:
    policy = WorkspaceSecurityPolicy(workspace_root)
    # validate path itself
    full_path = policy.validate_path(path)
    
    entries = []
    for entry in os.scandir(full_path):
        rel_path = os.path.relpath(entry.path, workspace_root)
        if policy.is_ignored(rel_path):
            continue
            
        entries.append({
            "name": entry.name,
            "type": "directory" if entry.is_dir() else "file",
            "size": entry.stat().st_size if entry.is_file() else None
        })
        
    return {"entries": entries}

def grep_search(workspace_root: str, pattern: str, path: str = ".", case_insensitive: bool = False) -> dict:
    policy = WorkspaceSecurityPolicy(workspace_root)
    full_search_path = policy.validate_path(path)
    
    matches = []
    regex_flags = re.IGNORECASE if case_insensitive else 0
    try:
        compiled_pattern = re.compile(pattern, regex_flags)
    except re.error:
        return {"matches": []}
        
    for root, dirs, files in os.walk(full_search_path):
        rel_root = os.path.relpath(root, workspace_root)
        
        # filter dirs
        valid_dirs = []
        for d in dirs:
            rel_d = os.path.normpath(os.path.join(rel_root, d))
            if rel_d.startswith(f".{os.sep}"):
                rel_d = rel_d[2:]
            if not policy.is_ignored(rel_d):
                valid_dirs.append(d)
        dirs[:] = valid_dirs
        
        for f in files:
            rel_file = os.path.normpath(os.path.join(rel_root, f))
            if rel_file.startswith(f".{os.sep}"):
                rel_file = rel_file[2:]
            if rel_file == f:
                 pass # handles root correctly
            if policy.is_ignored(rel_file):
                continue
                
            full_file = os.path.join(root, f)
            try:
                with open(full_file, "r", encoding="utf-8") as file_obj:
                    for line_num, line in enumerate(file_obj, 1):
                        if compiled_pattern.search(line):
                            matches.append({
                                "path": rel_file,
                                "line": line_num,
                                "content": line.rstrip('\n')
                            })
                            if len(matches) >= 100:
                                return {"matches": matches}
            except UnicodeDecodeError:
                continue # Skip binary files
                
    return {"matches": matches}
