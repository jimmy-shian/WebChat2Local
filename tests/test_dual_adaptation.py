import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

def adapt_response_for_tools(
    full_text: str,
    available_tool_names: List[str]
) -> Tuple[str, Optional[List[Dict[str, Any]]], str]:
    """
    Robust Dual-Adaptation Engine:
    1. Returns guaranteed XML-tagged content for clients expecting XML tool calls.
    2. Returns standard OpenAI tool_calls for clients expecting native function calls.
    3. Returns the appropriate finish_reason ("tool_calls" or "stop").
    """
    if not full_text:
        return full_text, None, "stop"

    clean_text = full_text.strip()
    
    # 1. Check if the text already contains explicit XML tool tags
    has_xml_tool = False
    for tool_name in available_tool_names:
        if f"<{tool_name}" in clean_text and f"</{tool_name}>" in clean_text:
            has_xml_tool = True
            break

    # 2. Extract tool_calls
    tool_calls = []
    if has_xml_tool:
        for tool_name in available_tool_names:
            pattern = rf"<{tool_name}(?:\s+[^>]*)?>(.*?)</{tool_name}>"
            matches = re.findall(pattern, clean_text, re.DOTALL)
            for match in matches:
                inner = match.strip()
                args = {}
                param_matches = re.findall(r"<([a-zA-Z0-9_-]+)>(.*?)</\1>", inner, re.DOTALL)
                if param_matches:
                    for param_name, param_val in param_matches:
                        args[param_name] = param_val.strip()
                else:
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
        final_content = clean_text
    else:
        # If no explicit XML tool tag was outputted, but attempt_completion is among available tools:
        if "attempt_completion" in available_tool_names:
            # Wrap the text in XML <attempt_completion><result>...</result></attempt_completion>
            final_content = f"<attempt_completion>\n<result>\n{clean_text}\n</result>\n</attempt_completion>"
            call_id = f"call_{uuid.uuid4().hex[:12]}"
            tool_calls.append({
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "attempt_completion",
                    "arguments": json.dumps({"result": clean_text}, ensure_ascii=False)
                }
            })
        else:
            final_content = clean_text

    finish_reason = "tool_calls" if (tool_calls and len(tool_calls) > 0) else "stop"
    return final_content, (tool_calls if tool_calls else None), finish_reason

def test_dual_adaptation():
    tools = ["attempt_completion", "read_file", "write_to_file", "execute_command"]

    # Case 1: Plain conversational answer without XML tags
    text1 = "這是 Jimmy's Tools 的專案，index.html 是首頁。"
    content1, tool_calls1, finish1 = adapt_response_for_tools(text1, tools)
    print("--- Test 1 (Plain text fallback) ---")
    print("Content:", repr(content1))
    print("Tool Calls:", json.dumps(tool_calls1, indent=2, ensure_ascii=False))
    print("Finish Reason:", finish1)
    assert "<attempt_completion>" in content1
    assert "<result>" in content1
    assert finish1 == "tool_calls"
    assert tool_calls1[0]["function"]["name"] == "attempt_completion"

    # Case 2: Already has <attempt_completion><result>
    text2 = "<attempt_completion><result>任務已完成，包含9個工具。</result></attempt_completion>"
    content2, tool_calls2, finish2 = adapt_response_for_tools(text2, tools)
    print("\n--- Test 2 (Explicit attempt_completion) ---")
    print("Content:", repr(content2))
    print("Tool Calls:", json.dumps(tool_calls2, indent=2, ensure_ascii=False))
    print("Finish Reason:", finish2)
    assert finish2 == "tool_calls"
    assert tool_calls2[0]["function"]["name"] == "attempt_completion"

    # Case 3: Action tool (read_file)
    text3 = "<read_file><path>index.html</path></read_file>"
    content3, tool_calls3, finish3 = adapt_response_for_tools(text3, tools)
    print("\n--- Test 3 (read_file action tool) ---")
    print("Content:", repr(content3))
    print("Tool Calls:", json.dumps(tool_calls3, indent=2, ensure_ascii=False))
    print("Finish Reason:", finish3)
    assert finish3 == "tool_calls"
    assert tool_calls3[0]["function"]["name"] == "read_file"

    print("\nAll Dual-Adaptation Tests Passed!")

if __name__ == "__main__":
    test_dual_adaptation()
