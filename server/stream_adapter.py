import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional


def extract_tools_from_text(text: str, available_tool_names: List[str]) -> Optional[List[Dict[str, Any]]]:
    """
    Intelligently converts model responses (XML tool calls or conversational answers)
    into standard OpenAI tool_calls objects for Cline, Roo Code, and AI agents.
    """
    if not text or not available_tool_names:
        return None

    tool_calls = []

    # 1. Match XML tags like <tool_name ...>...</tool_name>
    for tool_name in available_tool_names:
        pattern = rf"<{tool_name}(?:\s+[^>]*)?>(.*?)</{tool_name}>"
        matches = re.findall(pattern, text, re.DOTALL)
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

    if tool_calls:
        return tool_calls

    # 2. Synthesize attempt_completion if Cline expected tool usage and got an answer
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


def format_sse_chunk(
    chunk_id: str,
    model: str,
    content_delta: Optional[str] = None,
    role: Optional[str] = None,
    finish_reason: Optional[str] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Formats an OpenAI-compatible SSE chunk string with optional tool_calls support."""
    delta: Dict[str, Any] = {}
    if role:
        delta["role"] = role
    if content_delta is not None:
        delta["content"] = content_delta
    if tool_calls:
        # OpenAI spec requires each streamed tool_call to carry an "index" field,
        # otherwise clients like Cline / Roo Code fail to reassemble the call.
        indexed_calls = []
        for i, call in enumerate(tool_calls):
            indexed = dict(call)
            indexed["index"] = i
            indexed_calls.append(indexed)
        delta["tool_calls"] = indexed_calls

    payload = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def format_sse_done() -> str:
    """Formats the OpenAI-compatible stream terminator."""
    return "data: [DONE]\n\n"


def format_non_stream_response(
    response_id: str,
    model: str,
    content: str,
    finish_reason: str = "stop",
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> dict:
    """Formats an OpenAI-compatible non-streaming response dictionary."""
    message: Dict[str, Any] = {
        "role": "assistant",
    }
    if content:
        message["content"] = content
    if tool_calls:
        message["tool_calls"] = tool_calls
        finish_reason = "tool_calls"

    return {
        "id": response_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": len(content) // 4,
            "completion_tokens": len(content) // 4,
            "total_tokens": len(content) // 2,
        },
    }
