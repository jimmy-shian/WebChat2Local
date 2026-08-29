import json
import re
import os
from typing import Tuple, List, Dict, Any, Optional

def clean_json_text(text: str) -> str:
    """Fixes common LLM JSON syntax issues like unescaped Windows backslashes."""
    # Replace backslashes that are not valid JSON escape sequences with forward slash
    cleaned = re.sub(r'\\(?![/\"bfnrtu])', r'/', text)
    return cleaned

def extract_json_objects(text: str):
    """Yields parsed JSON objects from text with robust error tolerance."""
    for raw in [text, clean_json_text(text)]:
        for i, char in enumerate(raw):
            if char == '{':
                brace_count = 1
                for j in range(i + 1, len(raw)):
                    if raw[j] == '{':
                        brace_count += 1
                    elif raw[j] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            snippet = raw[i:j+1]
                            try:
                                yield json.loads(snippet)
                            except json.JSONDecodeError:
                                # Try cleaning unescaped quotes or slashes
                                try:
                                    fixed_snippet = re.sub(r'\\(?![/\"bfnrtu])', r'/', snippet)
                                    yield json.loads(fixed_snippet)
                                except Exception:
                                    pass
                            break

def parse_tool_response(text: str, available_tool_names: list[str]) -> tuple[str, list[dict] | None, str]:
    if not available_tool_names:
        return text, None, "stop"

    # 1. Standard / Cleaned JSON extraction
    for obj in extract_json_objects(text):
        if isinstance(obj, dict) and "tool" in obj and "arguments" in obj:
            tool_name = obj["tool"]
            args = obj["arguments"]
            if tool_name in available_tool_names and isinstance(args, dict):
                tool_calls = [{
                    "id": f"call_{tool_name}",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(args, ensure_ascii=False)
                    }
                }]
                return text, tool_calls, "tool_calls"

    # 2. Robust Regex Fallback for LLMs outputting loose JSON syntax
    for t_name in available_tool_names:
        if t_name == "create_file":
            # Match {"tool":"create_file" ... "path":"..." ... "content":"..."}
            m_path = re.search(r'["\']path["\']\s*:\s*["\']([^"\']+)["\']', text)
            m_content = re.search(r'["\']content["\']\s*:\s*["\']([\s\S]*?)["\']\s*[\},]', text)
            if "create_file" in text and m_path:
                path_val = m_path.group(1).replace("\\", "/").split("/")[-1]
                content_val = m_content.group(1) if m_content else ""
                args = {"path": path_val, "content": content_val}
                tool_calls = [{
                    "id": "call_create_file",
                    "type": "function",
                    "function": {
                        "name": "create_file",
                        "arguments": json.dumps(args, ensure_ascii=False)
                    }
                }]
                return text, tool_calls, "tool_calls"

        elif t_name == "run_command":
            m_cmd = re.search(r'["\']command["\']\s*:\s*["\']([^"\']+)["\']', text)
            if "run_command" in text and m_cmd:
                args = {"command": m_cmd.group(1)}
                tool_calls = [{
                    "id": "call_run_command",
                    "type": "function",
                    "function": {
                        "name": "run_command",
                        "arguments": json.dumps(args, ensure_ascii=False)
                    }
                }]
                return text, tool_calls, "tool_calls"

    if "attempt_completion" in available_tool_names:
        tool_calls = [{
            "id": "call_attempt_completion",
            "type": "function",
            "function": {
                "name": "attempt_completion",
                "arguments": json.dumps({"result": text.strip()}, ensure_ascii=False)
            }
        }]
        return text, tool_calls, "tool_calls"

    return text, None, "stop"

def format_tool_prompt(tools: list[dict]) -> str:
    if not tools:
        return ""
    
    tools_str = ""
    for t in tools:
        name = t.get("name", "")
        params = t.get("parameters", {}).get("properties", {})
        param_list = ", ".join(f'"{k}": "..."' for k in params.keys())
        tools_str += f'- {name}: {{"tool": "{name}", "arguments": {{{param_list}}}}}\n'

    return f"""【可用工具與 JSON 呼叫格式】
你是一個專業的任務執行 AI。當需要執行動作時，必須輸出 JSON 工具呼叫格式：
```json
{{"tool": "tool_name", "arguments": {{"param1": "value1"}}}}
```

可用工具清單：
{tools_str}
【絕對執行規則】
1. 若需執行指令或操作檔案，【直接】輸出對應工具的 JSON 格式。
2. 檔案路徑一律使用【相對路徑】（例如 "New.txt" 或 "src/index.js"），嚴禁使用 "C:\\..." 絕對路徑。路徑分隔符請一律使用正斜線 "/"。
3. 若使用者僅進行純問答，不需使用工具，請直接用文字回答。
4. 每次回覆【最多只能】輸出一個工具呼叫。執行後等待結果。
5. 當所有任務完成時，使用 `attempt_completion` 工具總結。
"""

def format_messages_for_web(messages: list[dict], tools: list[dict]) -> str:
    if not messages:
        return ""

    conversation_turns = []
    custom_system_note = ""

    AUTO_ERROR_PATTERNS = [
        re.compile(r'\[ERROR\]\s*You did not use a tool', re.IGNORECASE),
        re.compile(r'# Reminder:\s*Instructions for Tool Use', re.IGNORECASE),
        re.compile(r'Please share this file with .*? Support', re.IGNORECASE),
    ]

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        text = content if isinstance(content, str) else json.dumps(content)
        if not text or not text.strip():
            continue

        if role == "system":
            if "You are Cline" not in text and "environment_details" not in text:
                custom_system_note = text.strip()
        elif role == "user":
            is_auto_error = any(p.search(text) for p in AUTO_ERROR_PATTERNS)
            if not is_auto_error:
                cleaned_text = re.sub(r'<environment_details>[\s\S]*?</environment_details>', '', text, flags=re.IGNORECASE).strip()
                if cleaned_text:
                    conversation_turns.append({"role": "User", "text": cleaned_text})
        elif role == "assistant":
            conversation_turns.append({"role": "Assistant", "text": text.strip()})
        else:
            conversation_turns.append({"role": role, "text": text.strip()})

    formatted_parts = []
    if custom_system_note:
        formatted_parts.append(custom_system_note)

    if len(conversation_turns) == 1 and conversation_turns[0]["role"] == "User":
        formatted_parts.append(conversation_turns[0]["text"])
    else:
        for turn in conversation_turns:
            formatted_parts.append(f"[{turn['role']}]:\n{turn['text']}")

    tool_header = format_tool_prompt(tools)
    if tool_header:
        return tool_header + "\n\n" + "\n\n".join(formatted_parts)
    return "\n\n".join(formatted_parts)
