from enum import Enum, auto
from typing import Tuple, Dict, List, Optional

class PermissionLevel(Enum):
    AUTO = auto()
    CONFIRM = auto()
    SESSION_ALLOW = auto()
    DENY = auto()

class AgentMode(Enum):
    ASK = auto()
    PLAN = auto()
    CODE = auto()
    DEBUG = auto()
    AGENT = auto()

class ToolPermissionPolicy:
    def __init__(self):
        self.autopilot = False
        self.session_allow_lists: Dict[str, Dict[str, set]] = {}
        
        self.default_rules = {
            "read_file": PermissionLevel.AUTO,
            "list_directory": PermissionLevel.AUTO,
            "grep_search": PermissionLevel.AUTO,
            "create_file": PermissionLevel.CONFIRM,
            "edit_file": PermissionLevel.CONFIRM,
            "delete_file": PermissionLevel.CONFIRM,
            "run_command": PermissionLevel.CONFIRM
        }
        
        self.safe_commands = {"pytest", "npm test", "git status"}
        
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
        if tool_name not in self.default_rules:
            return PermissionLevel.DENY, f"Unknown tool {tool_name}"
            
        base_level = self.default_rules[tool_name]
        
        if tool_name == "run_command":
            cmd = arguments.get("command", "")
            if any(cmd.startswith(safe_cmd) for safe_cmd in self.safe_commands):
                return PermissionLevel.SESSION_ALLOW, "Safe command"
        
        if session_id and session_id in self.session_allow_lists:
            if tool_name in self.session_allow_lists[session_id]:
                allowed_cmds = self.session_allow_lists[session_id][tool_name]
                if "*" in allowed_cmds:
                    return PermissionLevel.SESSION_ALLOW, "Session allowed tool"
                if tool_name == "run_command" and "command" in arguments:
                    if arguments["command"] in allowed_cmds:
                        return PermissionLevel.SESSION_ALLOW, "Session allowed command"
                        
        if self.autopilot and base_level == PermissionLevel.CONFIRM and tool_name in ["create_file", "edit_file"]:
            return PermissionLevel.AUTO, "Autopilot enabled"
            
        return base_level, "Default policy"
        
    def get_available_tools_for_mode(self, mode: AgentMode) -> List[str]:
        if mode == AgentMode.ASK:
            return []
        elif mode == AgentMode.PLAN:
            return ["read_file", "list_directory", "grep_search"]
        elif mode == AgentMode.CODE:
            return ["read_file", "list_directory", "grep_search", "create_file", "edit_file"]
        elif mode == AgentMode.DEBUG:
            return ["read_file", "list_directory", "grep_search", "run_command"]
        elif mode == AgentMode.AGENT:
            return list(self.default_rules.keys())
        return []
