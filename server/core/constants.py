from enum import Enum

class ProviderName(str, Enum):
    AUTO = "auto"
    CHATGPT = "ChatGPT"
    GEMINI = "Gemini"
    DEEPSEEK = "DeepSeek"

class ToolName(str, Enum):
    READ_FILE = "read_file"
    EDIT_FILE = "edit_file"
    CREATE_FILE = "create_file"
    DELETE_FILE = "delete_file"
    LIST_DIRECTORY = "list_directory"
    GREP_SEARCH = "grep_search"
    RUN_COMMAND = "run_command"
    ATTEMPT_COMPLETION = "attempt_completion"

class EventType(str, Enum):
    MESSAGE_CHUNK = "message.chunk"
    TOOL_REQUEST = "tool.request"
    TOOL_EXECUTED = "tool.executed"
    EDIT_PROPOSED = "edit.proposed"
    EDIT_APPLIED = "edit.applied"
    AGENT_COMPLETED = "agent.completed"
    ERROR = "error"

class PermissionLevel(str, Enum):
    AUTO = "AUTO"
    CONFIRM = "CONFIRM"
    SESSION_ALLOW = "SESSION_ALLOW"
    DENY = "DENY"

class AgentMode(str, Enum):
    ASK = "ASK"
    PLAN = "PLAN"
    CODE = "CODE"
    DEBUG = "DEBUG"
    AGENT = "AGENT"

# Canonical Tool Specifications
CANONICAL_TOOLS = [
    {
        "name": ToolName.READ_FILE.value,
        "description": "讀取指定工作區檔案內容與 SHA-256 修訂號。支援選擇查看特定行數範圍。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相對於工作區根目錄的檔案路徑"},
                "start_line": {"type": "integer", "description": "選填。起始行號 (從 1 起算，含此行)。用於大檔案分段檢視。"},
                "end_line": {"type": "integer", "description": "選填。結束行號 (含此行)。用於大檔案分段檢視。"}
            },
            "required": ["path"]
        }
    },
    {
        "name": ToolName.CREATE_FILE.value,
        "description": "在工作區中建立新檔案並寫入初始內容。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "欲建立的檔案路徑"},
                "content": {"type": "string", "description": "檔案初始內容"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": ToolName.EDIT_FILE.value,
        "description": "對指定檔案進行精準文字替換修改，需提供讀取時獲得的 base_revision。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "欲修改的檔案路徑"},
                "revision": {"type": "string", "description": "檔案讀取時的 SHA-256 修訂號 (sha256:...)"},
                "edits": {
                    "type": "array",
                    "description": "欲替換的代碼片段清單",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_text": {"type": "string", "description": "欲被替換的原始文字（必須唯一且完全精確吻合）"},
                            "new_text": {"type": "string", "description": "替換後的新文字"}
                        },
                        "required": ["old_text", "new_text"]
                    }
                }
            },
            "required": ["path", "revision", "edits"]
        }
    },
    {
        "name": ToolName.DELETE_FILE.value,
        "description": "安全刪除指定檔案，需提供目前的 SHA-256 修訂號。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "欲刪除的檔案路徑"},
                "revision": {"type": "string", "description": "檔案目前的修訂號"}
            },
            "required": ["path", "revision"]
        }
    },
    {
        "name": ToolName.LIST_DIRECTORY.value,
        "description": "列出指定目錄下的子目錄與檔案清單（自動略過受保護與隱藏檔案）。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目錄路徑，預設為當前目錄 '.'"}
            },
            "required": []
        }
    },
    {
        "name": ToolName.GREP_SEARCH.value,
        "description": "在工作區代碼檔案中進行關鍵字或正則全文檢索。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "欲搜尋的關鍵字或正則表達式"},
                "path": {"type": "string", "description": "搜尋目錄範圍，預設為 '.'"},
                "case_insensitive": {"type": "boolean", "description": "是否忽略大小寫，預設為 false"}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": ToolName.RUN_COMMAND.value,
        "description": "在工作區執行終端機命令 (PowerShell)。",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "欲執行的指令字串"}
            },
            "required": ["command"]
        }
    }
]
