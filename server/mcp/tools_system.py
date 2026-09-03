"""
System diagnostic and workspace status tools for MCP server.
"""

import sys
import platform
import psutil
from pathlib import Path
from typing import Dict, Any
from server.config import get_workspace_root, SERVER_HOST, SERVER_PORT, BASE_URL


def get_workspace_status() -> Dict[str, Any]:
    """
    Get current workspace and bridge runtime diagnostic information.
    """
    workspace = get_workspace_root()
    process = psutil.Process()
    mem_info = process.memory_info()
    
    return {
        "status": "healthy",
        "workspace_root": str(workspace),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "bridge_server_url": BASE_URL,
        "memory_rss_mb": round(mem_info.rss / (1024 * 1024), 2),
        "cpu_percent": process.cpu_percent(interval=0.1),
    }


def doctor() -> Dict[str, Any]:
    """
    Perform self-diagnostics for the bridge server and MCP environment.
    """
    workspace = get_workspace_root()
    checks = []
    
    # Check workspace write permissions
    test_file = workspace / ".w2l_doctor_probe.tmp"
    can_write = False
    try:
        test_file.write_text("probe", encoding="utf-8")
        test_file.unlink()
        can_write = True
        checks.append({"check": "workspace_write", "passed": True, "message": "Workspace is writable."})
    except Exception as e:
        checks.append({"check": "workspace_write", "passed": False, "message": f"Workspace write error: {e}"})
        
    # Check python environment
    checks.append({
        "check": "python_runtime",
        "passed": True,
        "message": f"Running Python {sys.version.split()[0]} on Windows."
    })
    
    all_passed = all(c["passed"] for c in checks)
    return {
        "status": "healthy" if all_passed else "warning",
        "checks": checks,
    }
