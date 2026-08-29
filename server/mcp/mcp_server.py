import os
import asyncio
import json
import hashlib
from pathlib import Path
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("webchat2local-studio")

IGNORED_NAMES = {".git", "node_modules", ".venv", "dist", "build"}
IGNORED_FILES = {".env"}

def is_ignored(p: Path) -> bool:
    if p.name in IGNORED_NAMES or p.name in IGNORED_FILES:
        return True
    if p.suffix in (".pem", ".key") or p.name.startswith("credentials."):
        return True
    return False

def get_workspace_root() -> Path:
    return Path(os.getenv("W2L_WORKSPACE", os.getcwd())).resolve()

def resolve_path(path: str) -> Path:
    workspace = get_workspace_root()
    p = Path(path)
    if str(p).startswith("\\\\"):
        raise ValueError("UNC paths are not allowed")
    if not p.is_absolute():
        p = workspace / p
    p = p.resolve()
    
    if not str(p).startswith(str(workspace)):
        raise ValueError("Path traversal attempt detected")
    return p

def _compute_revision(p: Path) -> str:
    content = p.read_bytes()
    return "sha256:" + hashlib.sha256(content).hexdigest()

@mcp.tool()
def read_file(path: str) -> str:
    """Read a file from the workspace"""
    p = resolve_path(path)
    if not p.exists():
        raise FileNotFoundError(f"File {path} not found")
    content = p.read_text(encoding="utf-8")
    rev = _compute_revision(p)
    data = {"path": path, "revision": rev, "content": content}
    return f"Content:\n{content}\n\nStructured:\n{json.dumps(data)}"

@mcp.tool()
def edit_file(path: str, revision: str, edits: list[dict]) -> str:
    """Edit a file using exact text replacements"""
    p = resolve_path(path)
    if not p.exists():
        raise FileNotFoundError(f"File {path} not found")
    
    current_rev = _compute_revision(p)
    if current_rev != revision:
        return json.dumps({"error": "STALE_FILE", "message": f"Expected revision {revision}, got {current_rev}"})
    
    content = p.read_text(encoding="utf-8")
    for edit in edits:
        old_t = edit.get("old_text", "")
        new_t = edit.get("new_text", "")
        count = content.count(old_t)
        if count == 0:
            # Try CRLF/LF fallback
            alt_old_t = old_t.replace("\r\n", "\n") if "\r\n" in old_t else old_t.replace("\n", "\r\n")
            if content.count(alt_old_t) == 1:
                content = content.replace(alt_old_t, new_t, 1)
            else:
                return json.dumps({"error": "EDIT_MISMATCH", "message": "old_text not found exactly once"})
        elif count > 1:
            return json.dumps({"error": "AMBIGUOUS_MATCH", "message": "old_text found multiple times"})
        else:
            content = content.replace(old_t, new_t, 1)
            
    p.write_text(content, encoding="utf-8")
    return json.dumps({"status": "success", "revision": _compute_revision(p)})

@mcp.tool()
def create_file(path: str, content: str) -> str:
    """Create a new file"""
    p = resolve_path(path)
    if p.exists():
        raise FileExistsError(f"File {path} already exists")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return json.dumps({"status": "success", "revision": _compute_revision(p)})

@mcp.tool()
def delete_file(path: str, revision: str) -> str:
    """Delete a file"""
    p = resolve_path(path)
    if p.exists():
        current_rev = _compute_revision(p)
        if current_rev != revision:
             return json.dumps({"error": "STALE_FILE", "message": "Revision mismatch before deletion"})
        p.unlink()
    return json.dumps({"status": "success"})

@mcp.tool()
def list_directory(path: str = ".") -> str:
    """List directory contents"""
    p = resolve_path(path)
    entries = []
    if p.is_dir():
        for child in p.iterdir():
            if is_ignored(child):
                continue
            entries.append({
                "name": child.name,
                "type": "directory" if child.is_dir() else "file",
                "size": child.stat().st_size if child.is_file() else 0
            })
    return json.dumps(entries)

@mcp.tool()
def grep_search(pattern: str, path: str = ".", case_insensitive: bool = False) -> str:
    """Search for text patterns in files"""
    import re
    p = resolve_path(path)
    matches = []
    flags = re.IGNORECASE if case_insensitive else 0
    if p.is_file():
        files = [p] if not is_ignored(p) else []
    else:
        files = []
        for f in p.rglob("*"):
            if not f.is_file():
                continue
            if any(is_ignored(parent) for parent in f.parents):
                continue
            if is_ignored(f):
                continue
            files.append(f)
            
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines()):
                if re.search(pattern, line, flags):
                    matches.append({"file": str(f.relative_to(get_workspace_root())), "line": i+1, "content": line})
                    if len(matches) >= 100:
                        return json.dumps(matches)
        except UnicodeDecodeError:
            pass
    return json.dumps(matches)

@mcp.tool()
async def run_command(command: str, cwd: str = None) -> str:
    """Execute a terminal command"""
    try:
        proc_cwd = resolve_path(cwd) if cwd else get_workspace_root()
        proc = await asyncio.create_subprocess_shell(
            f"powershell -Command \"{command}\"",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(proc_cwd)
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        except asyncio.TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            return json.dumps({"exit_code": -1, "stdout": stdout.decode(errors="replace"), "stderr": "Command timed out"})
        
        return json.dumps({
            "exit_code": proc.returncode,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace")
        })
    except Exception as e:
        return json.dumps({"exit_code": -1, "stdout": "", "stderr": str(e)})

if __name__ == "__main__":
    mcp.run()
