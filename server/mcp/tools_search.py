"""
Search tools for MCP server: grep_search and find_files.
"""

import os
import re
import fnmatch
from pathlib import Path
from typing import Dict, Any, List, Optional
from server.config import get_workspace_root, IGNORED_DIRS, IGNORED_FILES, IGNORED_EXTENSIONS


def find_files(
    pattern: str,
    search_dir: str = ".",
    max_depth: int = 5,
    max_results: int = 50
) -> Dict[str, Any]:
    """
    Search for files matching a glob pattern within the workspace.
    
    Args:
        pattern: Glob pattern to match (e.g. '*.py', '*config*').
        search_dir: Directory to search within.
        max_depth: Maximum recursion depth.
        max_results: Maximum number of results to return.
    """
    workspace = get_workspace_root()
    p = Path(search_dir)
    if not p.is_absolute():
        p = workspace / p
    p = p.resolve()
    
    try:
        p.relative_to(workspace)
    except ValueError:
        return {"error": "ACCESS_DENIED", "message": "Search directory is outside workspace root."}
        
    if not p.exists() or not p.is_dir():
        return {"error": "INVALID_DIRECTORY", "message": f"'{search_dir}' is not a valid directory."}
        
    matches: List[Dict[str, Any]] = []
    
    def _walk(curr: Path, depth: int):
        if depth > max_depth or len(matches) >= max_results:
            return
        try:
            for item in curr.iterdir():
                if len(matches) >= max_results:
                    break
                if item.name in IGNORED_DIRS or item.name in IGNORED_FILES:
                    continue
                if fnmatch.fnmatch(item.name.lower(), pattern.lower()):
                    rel_path = str(item.relative_to(workspace)).replace("\\", "/")
                    matches.append({
                        "name": item.name,
                        "path": rel_path,
                        "is_dir": item.is_dir(),
                        "size": item.stat().st_size if item.is_file() else 0,
                    })
                if item.is_dir():
                    _walk(item, depth + 1)
        except PermissionError:
            pass
            
    _walk(p, 1)
    
    return {
        "status": "success",
        "pattern": pattern,
        "search_dir": str(p.relative_to(workspace)).replace("\\", "/") or ".",
        "total_matches": len(matches),
        "matches": matches,
    }


def grep_search(
    query: str,
    search_path: str = ".",
    is_regex: bool = False,
    case_sensitive: bool = False,
    max_results: int = 50
) -> Dict[str, Any]:
    """
    Search for text or regex patterns in workspace files.
    
    Args:
        query: Search string or regex pattern.
        search_path: File or directory to search in.
        is_regex: Whether query is a regular expression.
        case_sensitive: Whether match should be case-sensitive.
        max_results: Maximum matching lines to return.
    """
    workspace = get_workspace_root()
    p = Path(search_path)
    if not p.is_absolute():
        p = workspace / p
    p = p.resolve()
    
    try:
        p.relative_to(workspace)
    except ValueError:
        return {"error": "ACCESS_DENIED", "message": "Search path is outside workspace root."}
        
    if not p.exists():
        return {"error": "PATH_NOT_FOUND", "message": f"Path '{search_path}' does not exist."}
        
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        if is_regex:
            pattern = re.compile(query, flags)
        else:
            pattern = re.compile(re.escape(query), flags)
    except re.error as e:
        return {"error": "INVALID_REGEX", "message": str(e)}
        
    results: List[Dict[str, Any]] = []
    
    def _search_file(f: Path):
        if len(results) >= max_results:
            return
        if f.suffix in IGNORED_EXTENSIONS or f.name in IGNORED_FILES:
            return
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            for idx, line in enumerate(content.splitlines(), start=1):
                if pattern.search(line):
                    results.append({
                        "file": str(f.relative_to(workspace)).replace("\\", "/"),
                        "line": idx,
                        "content": line.strip()[:200],  # cap line length
                    })
                    if len(results) >= max_results:
                        break
        except Exception:
            pass

    if p.is_file():
        _search_file(p)
    else:
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            for file in files:
                _search_file(Path(root) / file)
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break
                
    return {
        "status": "success",
        "query": query,
        "is_regex": is_regex,
        "case_sensitive": case_sensitive,
        "total_matches": len(results),
        "matches": results,
    }
