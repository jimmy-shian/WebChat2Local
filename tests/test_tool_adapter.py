import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

def extract_tools_from_text(text: str, available_tool_names: List[str]) -> Optional[List[Dict[str, Any]]]:
    """
    Parses XML tool calls (e.g. <attempt_completion><result>...</result></attempt_completion>
    or <read_file><path>...</path></read_file>) from generated text into OpenAI tool_calls.
    """
    if not text:
        return None

    tool_calls = []

    # 1. Match XML tags like <tool_name ...>...</tool_name>
    for tool_name in available_tool_names:
        pattern = rf"<{tool_name}(?:\s+[^>]*)?>(.*?)</{tool_name}>"
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            inner = match.strip()
            args = {}
            # Check for inner parameters e.g. <result>...</result>, <path>...</path>, <command>...</command>
            param_matches = re.findall(r"<([a-zA-Z0-9_-]+)>(.*?)</\1>", inner, re.DOTALL)
            if param_matches:
                for param_name, param_val in param_matches:
                    args[param_name] = param_val.strip()
            else:
                # Default parameter
                if tool_name == "attempt_completion":
                    args["result"] = inner
                elif tool_name in ["read_file", "write_to_file"]:
                    args["path"] = inner
                elif tool_name == "execute_command":
                    args["command"] = inner
                elif tool_name == "ask_followup_question":
                    args["question"] = inner
                else:
                    args["content"] = inner

            call_id = f"call_{uuid.uuid4().hex[:12]}"
            tool_calls.append({
                "id": call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(args, ensure_ascii=False)
                }
            })

    if tool_calls:
        return tool_calls

    # 2. If no explicit XML tool tag was matched but attempt_completion is required in tools:
    if "attempt_completion" in available_tool_names and len(text.strip()) > 0:
        clean_text = text.replace("<attempt_completion>", "").replace("</attempt_completion>", "").strip()
        call_id = f"call_{uuid.uuid4().hex[:12]}"
        return [{
            "id": call_id,
            "type": "function",
            "function": {
                "name": "attempt_completion",
                "arguments": json.dumps({"result": clean_text}, ensure_ascii=False)
            }
        }]

    return None

def test_tool_adapter():
    tools = ["attempt_completion", "read_file", "execute_command", "ask_followup_question"]
    
    # Test Case 1: Pure text without explicit XML
    sample_text_1 = "你的專案是 Jimmy's Tools，index.html 是首頁入口。"
    res1 = extract_tools_from_text(sample_text_1, tools)
    print("Test 1 Result:", json.dumps(res1, indent=2, ensure_ascii=False))
    assert res1[0]["function"]["name"] == "attempt_completion"
    assert "Jimmy's Tools" in res1[0]["function"]["arguments"]

    # Test Case 2: Explicit XML tag with <result>
    sample_text_2 = "<attempt_completion><result>分析完成，首頁包含9個工具。</result></attempt_completion>"
    res2 = extract_tools_from_text(sample_text_2, tools)
    print("Test 2 Result:", json.dumps(res2, indent=2, ensure_ascii=False))
    assert res2[0]["function"]["name"] == "attempt_completion"
    assert "分析完成" in res2[0]["function"]["arguments"]

    # Test Case 3: Read file tool tag
    sample_text_3 = "<read_file><path>index.html</path></read_file>"
    res3 = extract_tools_from_text(sample_text_3, tools)
    print("Test 3 Result:", json.dumps(res3, indent=2, ensure_ascii=False))
    assert res3[0]["function"]["name"] == "read_file"
    assert "index.html" in res3[0]["function"]["arguments"]

    print("\n🎉🎉🎉 Tool Adapter Logic 100% Passed!")

if __name__ == "__main__":
    test_tool_adapter()
