"""
Shell command execution tool for MCP server.
Runs commands securely within workspace on Windows.
"""

import subprocess
import os
from pathlib import Path
from typing import Dict, Any, Optional
from server.config import get_workspace_root, DEFAULT_COMMAND_TIMEOUT


def run_command(
    command: str,
    cwd: Optional[str] = None,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT
) -> Dict[str, Any]:
    """
    Execute a shell command in the local workspace.
    
    Args:
        command: Command line string to execute (e.g. 'python -m pytest').
        cwd: Relative directory within workspace to execute in.
        timeout_seconds: Maximum time in seconds to wait for execution.
    """
    workspace = get_workspace_root()
    target_cwd = workspace
    
    if cwd:
        p = Path(cwd)
        if not p.is_absolute():
            p = workspace / p
        target_cwd = p.resolve()
        try:
            target_cwd.relative_to(workspace)
        except ValueError:
            return {
                "error": "SECURITY_ERROR",
                "message": f"Execution cwd '{cwd}' is outside the workspace root.",
                "exit_code": -1,
            }
            
    try:
        # Use PowerShell on Windows for consistent shell scripting
        shell_cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
        
        proc = subprocess.run(
            shell_cmd,
            cwd=str(target_cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace"
        )
        
        # Limit output length to prevent context explosion (64KB max)
        stdout = proc.stdout
        stderr = proc.stderr
        truncated = False
        
        if len(stdout) > 65536:
            stdout = stdout[:65536] + "\n... [stdout truncated at 64KB]"
            truncated = True
        if len(stderr) > 32768:
            stderr = stderr[:32768] + "\n... [stderr truncated at 32KB]"
            truncated = True
            
        return {
            "status": "success",
            "command": command,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": truncated,
        }
    except subprocess.TimeoutExpired:
        return {
            "error": "TIMEOUT",
            "message": f"Command timed out after {timeout_seconds} seconds.",
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
        }
    except Exception as e:
        return {
            "error": "EXECUTION_ERROR",
            "message": str(e),
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
        }
