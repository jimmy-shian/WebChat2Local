from typing import Tuple, Dict, List, Optional
from server.core.constants import PermissionLevel, AgentMode, ToolName

class ToolPermissionPolicy:
    def __init__(self, autopilot: bool = False):
        self.autopilot = autopilot
        self.session_allow_lists: Dict[str, Dict[str, set]] = {}
        
        self.default_rules = {
            ToolName.READ_FILE.value: PermissionLevel.AUTO,
            ToolName.LIST_DIRECTORY.value: PermissionLevel.AUTO,
            ToolName.GREP_SEARCH.value: PermissionLevel.AUTO,
            ToolName.CREATE_FILE.value: PermissionLevel.CONFIRM,
            ToolName.EDIT_FILE.value: PermissionLevel.CONFIRM,
            ToolName.DELETE_FILE.value: PermissionLevel.CONFIRM,
            ToolName.RUN_COMMAND.value: PermissionLevel.CONFIRM
        }
        
        self.safe_commands = {"pytest", "npm test", "git status", "dir", "echo"}
        
    def set_autopilot(self, enabled: bool):
        self.autopilot = enabled
        
    def grant_session_allow(self, session_id: str, tool_name: str, command: Optional[str] = None):
        if session_id not in self.session_allow_lists:
            self.session_allow_lists[session_id] = {}
        if tool_name not in self.session_allow_lists[session_id]:
            self.session_allow_lists[session_id][tool_name] = set()
        
        if command is not None:
            self.session_allow_lists[session_id][tool_name].add(command)
        else:
            self.session_allow_lists[session_id][tool_name].add("*")
            
    def check_permission(self, tool_name: str, arguments: dict, session_id: Optional[str] = None) -> Tuple[PermissionLevel, str]:
        if self.autopilot:
            return PermissionLevel.AUTO, "Autopilot enabled"

        if tool_name not in self.default_rules:
            return PermissionLevel.DENY, f"Unknown tool {tool_name}"
            
        base_level = self.default_rules[tool_name]
        
        if tool_name == ToolName.RUN_COMMAND.value:
            cmd = arguments.get("command", "")
            if any(cmd.startswith(safe_cmd) for safe_cmd in self.safe_commands):
                return PermissionLevel.SESSION_ALLOW, "Safe command"
        
        if session_id and session_id in self.session_allow_lists:
            if tool_name in self.session_allow_lists[session_id]:
                allowed_cmds = self.session_allow_lists[session_id][tool_name]
                if "*" in allowed_cmds:
                    return PermissionLevel.SESSION_ALLOW, "Session allowed"
                cmd = arguments.get("command", "")
                if cmd in allowed_cmds:
                    return PermissionLevel.SESSION_ALLOW, "Session allowed command"
                    
        return base_level, "Default policy"

    def get_available_tools_for_mode(self, mode: AgentMode | str) -> List[str]:
        mode_str = mode.value if isinstance(mode, AgentMode) else str(mode)
        
        if mode_str == AgentMode.ASK.value:
            return []
        elif mode_str == AgentMode.PLAN.value:
            return [
                ToolName.READ_FILE.value,
                ToolName.LIST_DIRECTORY.value,
                ToolName.GREP_SEARCH.value
            ]
        elif mode_str == AgentMode.CODE.value:
            return [
                ToolName.READ_FILE.value,
                ToolName.LIST_DIRECTORY.value,
                ToolName.GREP_SEARCH.value,
                ToolName.CREATE_FILE.value,
                ToolName.EDIT_FILE.value
            ]
        elif mode_str == AgentMode.DEBUG.value:
            return [
                ToolName.READ_FILE.value,
                ToolName.LIST_DIRECTORY.value,
                ToolName.GREP_SEARCH.value,
                ToolName.RUN_COMMAND.value
            ]
        elif mode_str == AgentMode.AGENT.value:
            return [
                ToolName.READ_FILE.value,
                ToolName.LIST_DIRECTORY.value,
                ToolName.GREP_SEARCH.value,
                ToolName.CREATE_FILE.value,
                ToolName.EDIT_FILE.value,
                ToolName.DELETE_FILE.value,
                ToolName.RUN_COMMAND.value
            ]
        return [
            ToolName.READ_FILE.value,
            ToolName.LIST_DIRECTORY.value,
            ToolName.GREP_SEARCH.value,
            ToolName.CREATE_FILE.value,
            ToolName.EDIT_FILE.value,
            ToolName.DELETE_FILE.value,
            ToolName.RUN_COMMAND.value
        ]
