import os
import platform
import json
from typing import List, Dict, Any, Optional
from server.core.constants import CANONICAL_TOOLS, ToolName

class SystemPromptBuilder:
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root

    def build_system_prompt(self, active_file: Optional[str] = None, custom_rules: Optional[str] = None) -> str:
        os_info = f"Windows {platform.version()} (PowerShell)" if platform.system() == "Windows" else platform.system()
        
        tools_list = []
        for t in CANONICAL_TOOLS:
            name = t["name"]
            desc = t["description"]
            props = t.get("parameters", {}).get("properties", {})
            param_spec = ", ".join([f'"{k}": "..."' for k in props.keys()])
            tools_list.append(f"- `{name}`: {desc}\n  語法範例: `{json.dumps({'tool': name, 'arguments': {k: '...' for k in props.keys()}}, ensure_ascii=False)}`")

        tools_block = "\n".join(tools_list)

        prompt = f"""你是一個運行在使用者本地開發環境 (WebChat2Local Studio) 內的自主 AI 程式工程師 (Autonomous Coding Agent)。
你擁有存取本地檔案系統與終端機的完整權限，並透過 JSON 工具呼叫 (Tool Calling) 直接在使用者本機上讀寫檔案與執行指令。

=== 本地環境資訊 (ENVIRONMENT DETAILS) ===
* 作業系統: {os_info}
* 工作區目錄: {self.workspace_root}
* 當前編輯中檔案: {active_file or '無'}

=== 可用本地工具規範 (CANONICAL TOOLS SPECIFICATION) ===
{tools_block}

=== 嚴格執行準則 (CRITICAL INSTRUCTIONS) ===
1. 【絕對執行權限】：你具備直接在本地建立、修改與刪除檔案的完整能力。嚴禁回覆「我無法存取您的本機檔案」或「請自行建立檔案」，必須【直接】輸出對應的 JSON 工具呼叫！
2. 【JSON 呼叫格式】：當需要讀取、建立、修改檔案或執行終端命令時，必須直接輸出單一且標準的 JSON 物件：
```json
{{"tool": "工具名稱", "arguments": {{"參數名": "數值"}}}}
```
3. 【單次單步執行】：每次回覆中【最多輸出一個】工具呼叫，等待後端執行並回傳結果後再進行下一步。
4. 【大檔案分段檢視】：讀取程式碼檔案時，若檔案較大，可指定 `start_line` 與 `end_line` 進行精準分段查看。
5. 【任務完成總結】：當所有檔案操作或使用者需求均已完整落實後，輸出純文字總結或 `attempt_completion` 工具。
"""
        if custom_rules:
            prompt += f"\n=== 使用者自訂專案規則 ===\n{custom_rules}\n"

        return prompt

    def build_full_user_prompt(self, user_prompt: str, active_file: Optional[str] = None, context_files: Optional[List[Dict[str, Any]]] = None) -> str:
        parts = []
        if context_files:
            for f in context_files:
                parts.append(f"=== 附加檔案上下文: {f['path']} ===\n{f.get('content', '')}\n")

        parts.append(user_prompt)
        return "\n\n".join(parts)
