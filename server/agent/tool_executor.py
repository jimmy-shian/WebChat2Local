import asyncio
import os
import time
from typing import Dict, Any, Tuple, Optional
from server.core.constants import ToolName, PermissionLevel
from server.tools.edit_engine import (
    read_file, edit_file, apply_proposal, create_file, delete_file, list_directory, grep_search
)

class ToolExecutor:
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root

    def normalize_path(self, path: str) -> str:
        if not path:
            return ""
        p = path.replace("\\", "/").strip()
        ws = os.path.abspath(self.workspace_root).replace("\\", "/").rstrip("/")
        if p.startswith(ws):
            p = p[len(ws):].lstrip("/")
        elif ":" in p and "/" in p:
            p = p.split("/")[-1]
        return p

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Executes a canonical tool and returns structured result."""
        try:
            if tool_name == ToolName.READ_FILE.value:
                path = self.normalize_path(arguments.get("path", ""))
                start_line = arguments.get("start_line")
                end_line = arguments.get("end_line")
                res = read_file(self.workspace_root, path, start_line, end_line)
                return {"success": True, "result": res}

            elif tool_name == ToolName.CREATE_FILE.value:
                path = self.normalize_path(arguments.get("path", ""))
                content = arguments.get("content", "")
                res = create_file(self.workspace_root, path, content)
                return res

            elif tool_name == ToolName.EDIT_FILE.value:
                path = arguments.get("path", "")
                revision = arguments.get("revision", "")
                edits = arguments.get("edits", [])
                if not revision:
                    try:
                        cur = read_file(self.workspace_root, path)
                        revision = cur["revision"]
                    except Exception:
                        revision = "sha256:unknown"
                res = edit_file(self.workspace_root, path, revision, edits)
                return res

            elif tool_name == ToolName.DELETE_FILE.value:
                path = arguments.get("path", "")
                revision = arguments.get("revision", "")
                if not revision:
                    try:
                        cur = read_file(self.workspace_root, path)
                        revision = cur["revision"]
                    except Exception:
                        revision = ""
                res = delete_file(self.workspace_root, path, revision)
                return res

            elif tool_name == ToolName.LIST_DIRECTORY.value:
                path = arguments.get("path", ".")
                res = list_directory(self.workspace_root, path)
                return {"success": True, "result": res}

            elif tool_name == ToolName.GREP_SEARCH.value:
                pattern = arguments.get("pattern", "")
                path = arguments.get("path", ".")
                case_insensitive = arguments.get("case_insensitive", False)
                res = grep_search(self.workspace_root, pattern, path, case_insensitive)
                return {"success": True, "result": res}

            elif tool_name == ToolName.RUN_COMMAND.value:
                cmd = arguments.get("command", "")
                full_cmd = f'powershell -NoProfile -NonInteractive -Command "{cmd}"'
                start_time = time.time()
                proc = await asyncio.create_subprocess_shell(
                    full_cmd,
                    cwd=self.workspace_root,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    stdout, stderr = await proc.communicate()

                exit_code = proc.returncode
                return {
                    "success": exit_code == 0,
                    "exit_code": exit_code,
                    "stdout": stdout.decode(errors="replace") if stdout else "",
                    "stderr": stderr.decode(errors="replace") if stderr else "",
                    "execution_time_ms": int((time.time() - start_time) * 1000)
                }

            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            return {"success": False, "error": str(e)}
