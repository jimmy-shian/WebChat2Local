import json
import re

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
2. 若使用者僅進行純問答，不需使用工具，請直接用文字回答。
3. 每次回覆【最多只能】輸出一個工具呼叫。執行後等待結果。
4. 當所有任務完成時，使用 `attempt_completion` 工具總結。
5. 若要修改檔案，請先使用讀取檔案工具獲取內容與版本號，再進行修改。
6. 嚴禁在動作未完成前呼叫 `attempt_completion`。
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
            if len(text) < 500 and "You are Cline" not in text and "environment_details" not in text:
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
        formatted_parts.append(f"[System Note]: {custom_system_note}")

    if len(conversation_turns) == 1 and conversation_turns[0]["role"] == "User":
        formatted_parts.append(conversation_turns[0]["text"])
    else:
        for turn in conversation_turns:
            formatted_parts.append(f"[{turn['role']}]:\n{turn['text']}")

    tool_header = format_tool_prompt(tools)
    if tool_header:
        return tool_header + "\n\n" + "\n\n".join(formatted_parts)
    return "\n\n".join(formatted_parts)

def extract_json_objects(text):
    for i, char in enumerate(text):
        if char == '{':
            brace_count = 1
            for j in range(i + 1, len(text)):
                if text[j] == '{':
                    brace_count += 1
                elif text[j] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        try:
                            yield json.loads(text[i:j+1])
                        except json.JSONDecodeError:
                            pass
                        break

def parse_tool_response(text: str, available_tool_names: list[str]) -> tuple[str, list[dict] | None, str]:
    if not available_tool_names:
        return text, None, "stop"

    for obj in extract_json_objects(text):
        if "tool" in obj and "arguments" in obj:
            tool_name = obj["tool"]
            args = obj["arguments"]
            if tool_name in available_tool_names and isinstance(args, dict):
                tool_calls = [{
                    "id": f"call_{tool_name}",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(args)
                    }
                }]
                return text, tool_calls, "tool_calls"

    if "attempt_completion" in available_tool_names:
        tool_calls = [{
            "id": "call_attempt_completion",
            "type": "function",
            "function": {
                "name": "attempt_completion",
                "arguments": json.dumps({"result": text.strip()})
            }
        }]
        return text, tool_calls, "tool_calls"

    return text, None, "stop"
