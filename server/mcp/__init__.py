"""
MCP (Model Context Protocol) Tools Package for Gemini Web to Local Bridge.
Provides unified dispatching for in-browser extension tunnel and API tool calls.
"""

from typing import Dict, Any, Optional
import json
import logging

from server.mcp.tools_filesystem import read_file, write_file, edit_file, list_dir, find_files
from server.mcp.tools_shell import run_command
from server.mcp.tools_search import grep_search
from server.mcp.tools_system import get_workspace_status, doctor

LOGGER = logging.getLogger("webchat2local.mcp")


def execute_mcp_tool(tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Execute a local workspace MCP tool by name and arguments.
    Used by the WebSocket tunnel and HTTP MCP endpoints.
    """
    args = arguments or {}
    name = (tool_name or "").strip().lower()

    try:
        if name in ("read_file", "view_file"):
            path = args.get("path") or args.get("file_path") or args.get("target_file") or "."
            start_line = int(args["start_line"]) if "start_line" in args and args["start_line"] is not None else None
            end_line = int(args["end_line"]) if "end_line" in args and args["end_line"] is not None else None
            return read_file(path=str(path), start_line=start_line, end_line=end_line)

        elif name in ("write_file", "write_to_file", "create_file"):
            path = args.get("path") or args.get("file_path") or args.get("target_file") or ""
            content = args.get("content") or args.get("code") or args.get("file_text") or ""
            overwrite = bool(args.get("overwrite", True))
            return write_file(path=str(path), content=str(content), overwrite=overwrite)

        elif name in ("edit_file", "replace_file_content", "apply_diff"):
            path = args.get("path") or args.get("file_path") or args.get("target_file") or ""
            search_target = args.get("search_target") or args.get("old_str") or args.get("target_content") or args.get("search") or ""
            replacement = args.get("replacement") or args.get("new_str") or args.get("replacement_content") or args.get("replace") or ""
            allow_multiple = bool(args.get("allow_multiple", False))
            return edit_file(path=str(path), search_target=str(search_target), replacement=str(replacement), allow_multiple=allow_multiple)

        elif name in ("list_dir", "list_files", "list_directory"):
            path = args.get("path") or args.get("directory_path") or "."
            recursive = bool(args.get("recursive", False))
            max_depth = int(args.get("max_depth", 2))
            return list_dir(path=str(path), recursive=recursive, max_depth=max_depth)

        elif name in ("find_files", "find_by_name"):
            pattern = args.get("pattern") or args.get("glob") or "*"
            path = args.get("path") or args.get("directory") or "."
            max_results = int(args.get("max_results", 100))
            return find_files(pattern=str(pattern), path=str(path), max_results=max_results)

        elif name in ("run_command", "execute_command", "bash", "terminal"):
            cmd = args.get("command") or args.get("cmd") or ""
            cwd = args.get("cwd")
            timeout_sec = int(args.get("timeout", args.get("timeout_seconds", 60)))
            return run_command(command=str(cmd), cwd=cwd, timeout_seconds=timeout_sec)

        elif name in ("grep_search", "search_files"):
            query = args.get("query") or args.get("pattern") or ""
            path = args.get("path") or "."
            file_pattern = args.get("file_pattern") or args.get("includes")
            return grep_search(query=str(query), path=str(path), file_pattern=file_pattern)

        elif name in ("get_workspace_status", "status", "workspace_status"):
            return get_workspace_status()

        elif name in ("doctor", "check_system"):
            return doctor()

        else:
            return {
                "status": "error",
                "error": f"Unknown tool: '{tool_name}'",
                "supported_tools": [
                    "read_file", "write_file", "edit_file", "list_dir",
                    "find_files", "run_command", "grep_search", "get_workspace_status"
                ]
            }

    except Exception as e:
        LOGGER.error("MCP execution error on '%s': %s", tool_name, str(e), exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "tool": tool_name,
        }

