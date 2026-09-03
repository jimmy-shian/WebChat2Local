"""
Filesystem tools for the MCP server.
Provides safe, sandboxed file operations within the workspace.
"""

import os
import fnmatch
from pathlib import Path
from typing import Dict, Any, List, Optional
from server.config import get_workspace_root, IGNORED_DIRS, IGNORED_FILES, IGNORED_EXTENSIONS


def _resolve_safe_path(path_str: str) -> Path:
    """Resolves and validates that the path is within the workspace root."""
    workspace = get_workspace_root()
    p = Path(path_str)
    
    if str(p).startswith("\\\\") or str(p).startswith("//"):
        raise ValueError("UNC network paths are not allowed.")
        
    if not p.is_absolute():
        p = workspace / p
    p = p.resolve()
    
    try:
        p.relative_to(workspace)
    except ValueError:
        raise ValueError(f"Access denied: path '{path_str}' is outside workspace root '{workspace}'.")
        
    return p


def _is_sensitive_or_ignored(p: Path) -> bool:
    """Checks if a path should be protected from AI modification/access."""
    for part in p.parts:
        if part in IGNORED_DIRS or part in IGNORED_FILES:
            return True
    if p.suffix in IGNORED_EXTENSIONS:
        return True
    return False


def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
    """
    Read content from a file in the workspace.
    
    Args:
        path: Path to the file (relative or absolute within workspace).
        start_line: 1-indexed start line number (inclusive).
        end_line: 1-indexed end line number (inclusive).
    """
    p = _resolve_safe_path(path)
    if not p.exists():
        return {"error": "FILE_NOT_FOUND", "message": f"File '{path}' does not exist."}
    if p.is_dir():
        return {"error": "IS_DIRECTORY", "message": f"Path '{path}' is a directory, not a file."}
    if _is_sensitive_or_ignored(p):
        return {"error": "ACCESS_DENIED", "message": f"File '{path}' is protected/ignored."}
        
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": "READ_ERROR", "message": str(e)}
        
    lines = content.splitlines(keepends=True)
    total_lines = len(lines)
    
    if start_line is not None or end_line is not None:
        s = max(1, start_line) if start_line else 1
        e = min(total_lines, end_line) if end_line else total_lines
        if s > total_lines:
            selected_content = ""
        else:
            selected_content = "".join(lines[s - 1 : e])
        return {
            "status": "success",
            "path": str(p.relative_to(get_workspace_root())),
            "total_lines": total_lines,
            "start_line": s,
            "end_line": e,
            "content": selected_content,
        }
        
    return {
        "status": "success",
        "path": str(p.relative_to(get_workspace_root())),
        "total_lines": total_lines,
        "content": content,
    }


def write_file(path: str, content: str, overwrite: bool = True) -> Dict[str, Any]:
    """
    Create or overwrite a file in the workspace.
    
    Args:
        path: Path to the target file.
        content: Text content to write.
        overwrite: Whether to overwrite if the file already exists.
    """
    p = _resolve_safe_path(path)
    if p.exists() and not overwrite:
        return {"error": "FILE_EXISTS", "message": f"File '{path}' already exists and overwrite is False."}
    if _is_sensitive_or_ignored(p):
        return {"error": "ACCESS_DENIED", "message": f"Target file '{path}' is protected/ignored."}
        
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {
            "status": "success",
            "path": str(p.relative_to(get_workspace_root())),
            "bytes_written": len(content.encode("utf-8")),
        }
    except Exception as e:
        return {"error": "WRITE_ERROR", "message": str(e)}


def edit_file(
    path: str,
    search_target: Optional[str] = None,
    replacement: Optional[str] = None,
    allow_multiple: bool = False,
    target_content: Optional[str] = None,
    replacement_content: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Edit a file by replacing occurrences of search_target with replacement.
    """
    # Accept both the current MCP argument names and the legacy test/client
    # names so older integrations do not silently lose edit capability.
    if search_target is None:
        search_target = target_content
    if replacement is None:
        replacement = replacement_content
    if search_target is None or replacement is None:
        return {"error": "INVALID_ARGUMENTS", "message": "search_target/replacement are required."}

    p = _resolve_safe_path(path)
    if not p.exists():
        return {"error": "FILE_NOT_FOUND", "message": f"File '{path}' does not exist."}
    if _is_sensitive_or_ignored(p):
        return {"error": "ACCESS_DENIED", "message": f"File '{path}' is protected."}
        
    try:
        content = p.read_text(encoding="utf-8")
    except Exception as e:
        return {"error": "READ_ERROR", "message": str(e)}
        
    count = content.count(search_target)
    
    # Handle CRLF vs LF differences if direct count is 0
    if count == 0:
        alt_target = search_target.replace("\r\n", "\n") if "\r\n" in search_target else search_target.replace("\n", "\r\n")
        alt_count = content.count(alt_target)
        if alt_count == 1:
            search_target = alt_target
            count = 1
            
    if count == 0:
        return {
            "error": "TARGET_NOT_FOUND",
            "message": "The exact search_target was not found in the file."
        }
    if count > 1 and not allow_multiple:
        return {
            "error": "AMBIGUOUS_MATCH",
            "message": f"search_target found {count} times. Provide more surrounding context or set allow_multiple=True."
        }
        
    new_content = content.replace(search_target, replacement, -1 if allow_multiple else 1)
    
    try:
        p.write_text(new_content, encoding="utf-8")
        return {
            "status": "success",
            "path": str(p.relative_to(get_workspace_root())),
            "replacements_made": count if allow_multiple else 1,
        }
    except Exception as e:
        return {"error": "WRITE_ERROR", "message": str(e)}


def delete_file(path: str) -> Dict[str, Any]:
    """Delete a file in the workspace."""
    p = _resolve_safe_path(path)
    if not p.exists():
        return {"error": "FILE_NOT_FOUND", "message": f"File '{path}' does not exist."}
    if _is_sensitive_or_ignored(p):
        return {"error": "ACCESS_DENIED", "message": f"Cannot delete protected file '{path}'."}
        
    try:
        if p.is_dir():
            p.rmdir()
        else:
            p.unlink()
        return {"status": "success", "deleted": str(p.relative_to(get_workspace_root()))}
    except Exception as e:
        return {"error": "DELETE_ERROR", "message": str(e)}


def list_dir(path: str = ".", recursive: bool = False, max_depth: int = 2) -> Dict[str, Any]:
    """
    List contents of a directory in the workspace.
    """
    p = _resolve_safe_path(path)
    if not p.exists():
        return {"error": "DIR_NOT_FOUND", "message": f"Directory '{path}' does not exist."}
    if not p.is_dir():
        return {"error": "NOT_A_DIRECTORY", "message": f"Path '{path}' is a file."}
        
    workspace = get_workspace_root()
    entries = []
    
    def _scan(curr: Path, depth: int):
        if depth > max_depth:
            return
        try:
            for item in curr.iterdir():
                if item.name in IGNORED_DIRS or item.name in IGNORED_FILES:
                    continue
                is_directory = item.is_dir()
                rel_path = str(item.relative_to(workspace)).replace("\\", "/")
                entry: Dict[str, Any] = {
                    "name": item.name,
                    "path": rel_path,
                    "is_dir": is_directory,
                }
                if not is_directory:
                    try:
                        entry["size"] = item.stat().st_size
                    except Exception:
                        entry["size"] = 0
                else:
                    if recursive and depth < max_depth:
                        _scan(item, depth + 1)
                entries.append(entry)
        except PermissionError:
            pass
            
    _scan(p, 1)
    return {
        "status": "success",
        "directory": str(p.relative_to(workspace)).replace("\\", "/") or ".",
        "total_items": len(entries),
        "items": entries[:200],
    }


def find_files(
    pattern: str = "*",
    path: str = ".",
    max_results: int = 50,
    search_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search for files matching a glob pattern within the workspace.
    """
    if search_dir is not None:
        path = search_dir
    p = _resolve_safe_path(path)
    if not p.exists() or not p.is_dir():
        return {"error": "DIR_NOT_FOUND", "message": f"Directory '{path}' not found."}

    workspace = get_workspace_root()
    matched = []

    for root, dirs, files in os.walk(p):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for f in files:
            if f in IGNORED_FILES:
                continue
            if fnmatch.fnmatch(f, pattern):
                full_p = Path(root) / f
                rel_p = str(full_p.relative_to(workspace)).replace("\\", "/")
                matched.append(rel_p)
                if len(matched) >= max_results:
                    break
        if len(matched) >= max_results:
            break

    return {
        "status": "success",
        "pattern": pattern,
        "matched_count": len(matched),
        "files": matched,
        # Backward-compatible shape used by the original local harness tests.
        "total_matches": len(matched),
        "matches": [
            {
                "name": Path(item).name,
                "path": item,
                "is_dir": False,
            }
            for item in matched
        ],
    }
