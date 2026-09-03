"""
Stream Adapter for formatting SSE outputs for OpenAI Chat Completions
and Codex/Antigravity Responses API.
Modeled after codex-chatgpt-web/src/bridge.ts.
"""

import json
import re
import time
import uuid
from typing import AsyncGenerator, Dict, Any, Optional

from server.bridge.ws_hub import TurnEvent
from server.protocol import (
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatMessage,
    ToolCall,
    FunctionCall,
)
from server.bridge.session_manager import SessionManager


def _is_transport_noise(text: str) -> bool:
    """Reject opaque Google transport strings accidentally selected as answers."""
    s = (text or "").strip()
    if not s:
        return False

    if re.fullmatch(r"^(?:https?:)?//\S+", s, re.IGNORECASE):
        return True
    if re.fullmatch(r"^\s*//?\[?www\.\S+", s, re.IGNORECASE):
        return True
    if re.fullmatch(r"https?://(?:[a-zA-Z0-9-]+\.)*(?:google\.com|googleusercontent\.com|gstatic\.com)/\S+", s, re.IGNORECASE):
        return True
    if re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+", s):
        return True
    if re.fullmatch(r"(?:台灣|臺灣|香港|澳門|日本|美國|中國|Taiwan|Hong Kong|Japan|USA)[\u4e00-\u9fa5A-Za-z0-9\s,.-]{0,35}(?:縣|市|區|里|鄉|鎮|村|路|段|District|City|County|State|Township)", s):
        return True
    if re.search(r"根據您的\s*(?:IP|位置|過去活動)|依據您的位置|Based on your (?:IP|location)|From your IP", s, re.IGNORECASE):
        return True

    # If the text has spaces, multiple lines, CJK characters, or markdown headers, it's real output
    if "\n" in s or " " in s:
        if len(s.split()) > 1 or re.search(r"[\u3000\u3400-\u9fff\u3040-\u30ff]", s):
            return False

    if re.fullmatch(r"[A-Za-z0-9_-]{12,}", s):
        return True
    if re.fullmatch(r"[A-Fa-f0-9]{12,}", s):
        return True
    return False


async def stream_openai_completions(
    event_generator: AsyncGenerator[TurnEvent, None],
    model: str = "gemini-web/pro",
    req_id: Optional[str] = None,
    available_tool_names: Optional[list[str]] = None,
) -> AsyncGenerator[str, None]:
    """
    Generates OpenAI-compatible SSE events (POST /v1/chat/completions?stream=true).
    Supports both content streaming and reasoning_content (thinking process) streaming.
    """
    completion_id = req_id or f"chatcmpl-{uuid.uuid4().hex[:16]}"
    created_ts = int(time.time())

    # Initial chunk with role="assistant"
    initial_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": ""},
                "finish_reason": None,
            }
        ],
    }
    yield f"data: {json.dumps(initial_chunk, ensure_ascii=False)}\n\n"

    last_text = ""
    last_thought = ""
    full_text = ""
    emitted_text = ""
    tool_mode = False
    pending_tool_prefix = ""

    def split_tool_boundary(delta: str):
        """Return safe text before a tool marker, buffering split XML prefixes.

        Gemini can split `<tool_call>` across arbitrary transport chunks.  If
        we forward `<tool_` from one chunk before recognizing the marker in the
        next chunk, Kilo/Cline sees malformed XML instead of a structured
        tool_calls response.
        """
        nonlocal pending_tool_prefix, tool_mode
        if tool_mode:
            return ""

        combined = pending_tool_prefix + delta
        pending_tool_prefix = ""

        marker_tokens = ["<tool_call>"]
        if available_tool_names:
            marker_tokens.extend(f"<{name}>" for name in available_tool_names)

        positions = [(combined.find(token), token) for token in marker_tokens if combined.find(token) >= 0]
        if positions:
            pos, _ = min(positions, key=lambda item: item[0])
            tool_mode = True
            return combined[:pos]

        # Hold only a suffix which could be the beginning of a marker.  Keep
        # the longest possible prefix so normal text is still streamed.
        prefix_lengths = []
        for token in marker_tokens:
            for n in range(1, min(len(token), len(combined)) + 1):
                if combined.endswith(token[:n]):
                    prefix_lengths.append(n)
        if prefix_lengths:
            n = max(prefix_lengths)
            pending_tool_prefix = combined[-n:]
            return combined[:-n]
        return combined

    async for event in event_generator:
        if event.type == "error":
            err_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": f"\n\n[Error: {event.error}]"},
                        "finish_reason": "stop",
                    }
                ],
            }
            yield f"data: {json.dumps(err_chunk, ensure_ascii=False)}\n\n"
            break

        # 1. Stream Thinking/Reasoning deltas if present
        if event.thought_delta:
            thought_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"reasoning_content": event.thought_delta},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(thought_chunk, ensure_ascii=False)}\n\n"
        elif event.thought and len(event.thought) > len(last_thought):
            diff = event.thought[len(last_thought):]
            last_thought = event.thought
            thought_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"reasoning_content": diff},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(thought_chunk, ensure_ascii=False)}\n\n"

        # 2. Stream content. Once a tool-call marker appears, hold the tool
        # payload back; the host client must receive structured tool_calls
        # rather than XML rendered as assistant text.
        incoming_delta = event.delta or ""
        if event.text and len(event.text) >= len(full_text):
            incoming_delta = event.text[len(full_text):]
            full_text = event.text
        elif incoming_delta:
            full_text += incoming_delta

        if not tool_mode:
            # Tool/XML tags can be split across browser stream chunks.  Once
            # we see a partial opening tag, hold it until the complete model
            # output is available instead of leaking XML to the client.
            safe_delta = split_tool_boundary(incoming_delta)
        else:
            safe_delta = ""

        if safe_delta:
            emitted_text += safe_delta
            content_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": safe_delta},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(content_chunk, ensure_ascii=False)}\n\n"

        last_text = full_text

        if event.type == "done":
            # A marker prefix may have been buffered at the end of the stream.
            # It is intentionally not emitted: the complete tool payload is
            # converted to structured tool_calls below when possible.
            break

    extracted_tools = SessionManager.extract_tool_calls(full_text, available_tool_names)
    if not extracted_tools and _is_transport_noise(full_text):
        full_text = ""
    finish_reason = "stop"
    if extracted_tools:
        finish_reason = "tool_calls"
        for index, tc in enumerate(extracted_tools):
            args_val = tc.get("arguments", {})
            if isinstance(args_val, dict):
                args_str = json.dumps(args_val, ensure_ascii=False)
            elif isinstance(args_val, str):
                args_str = args_val
            else:
                args_str = json.dumps(args_val, ensure_ascii=False)

            tool_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {
                        "tool_calls": [{
                            "index": index,
                            "id": f"call_{uuid.uuid4().hex[:12]}",
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": args_str,
                            },
                        }]
                    },
                    "finish_reason": None,
                }]
            }
            yield f"data: {json.dumps(tool_chunk, ensure_ascii=False)}\n\n"
    elif tool_mode and full_text and len(full_text) > len(emitted_text):
        # If tool mode suppressed text but no valid tools were extracted,
        # emit the suppressed text so no response is dropped.
        remaining = full_text[len(emitted_text):]
        if remaining:
            content_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": remaining},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(content_chunk, ensure_ascii=False)}\n\n"

    # Final termination chunk
    final_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": finish_reason,
            }
        ],
    }
    yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


async def stream_responses_api(
    event_generator: AsyncGenerator[TurnEvent, None],
    model: str = "gemini-web/pro",
    req_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Generates Codex/Antigravity Responses API SSE stream (POST /v1/responses).
    """
    resp_id = req_id or f"resp_{uuid.uuid4().hex[:16]}"
    item_id = f"item_{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    # 1. response.created
    yield f"event: response.created\ndata: {json.dumps({'id': resp_id, 'model': model, 'status': 'in_progress', 'created_at': created_ts})}\n\n"

    # 2. response.output_item.added
    yield f"event: response.output_item.added\ndata: {json.dumps({'response_id': resp_id, 'output_index': 0, 'item': {'id': item_id, 'type': 'message', 'role': 'assistant', 'content': []}})}\n\n"

    last_text = ""
    last_thought = ""

    async for event in event_generator:
        if event.type == "error":
            yield f"event: response.failed\ndata: {json.dumps({'response_id': resp_id, 'error': {'type': 'bridge_error', 'message': event.error}})}\n\n"
            return

        # Thinking delta
        if event.thought_delta:
            yield f"event: response.reasoning.delta\ndata: {json.dumps({'response_id': resp_id, 'item_id': item_id, 'delta': event.thought_delta})}\n\n"
        elif event.thought and len(event.thought) > len(last_thought):
            diff = event.thought[len(last_thought):]
            last_thought = event.thought
            yield f"event: response.reasoning.delta\ndata: {json.dumps({'response_id': resp_id, 'item_id': item_id, 'delta': diff})}\n\n"

        # Text delta
        if event.delta:
            yield f"event: response.text.delta\ndata: {json.dumps({'response_id': resp_id, 'item_id': item_id, 'delta': event.delta})}\n\n"
        elif event.text and len(event.text) > len(last_text):
            diff = event.text[len(last_text):]
            last_text = event.text
            yield f"event: response.text.delta\ndata: {json.dumps({'response_id': resp_id, 'item_id': item_id, 'delta': diff})}\n\n"

        if event.type == "done":
            break

    # 3. response.output_item.done
    yield f"event: response.output_item.done\ndata: {json.dumps({'response_id': resp_id, 'output_index': 0, 'item': {'id': item_id, 'type': 'message', 'role': 'assistant', 'status': 'completed', 'content': [{'type': 'text', 'text': last_text}]}})}\n\n"

    # 4. response.completed
    yield f"event: response.completed\ndata: {json.dumps({'id': resp_id, 'status': 'completed', 'model': model})}\n\n"


async def collect_complete_response(
    event_generator: AsyncGenerator[TurnEvent, None],
    model: str = "gemini-web/pro",
    available_tool_names: Optional[list[str]] = None,
) -> ChatCompletionResponse:
    """
    Consumes the turn stream and constructs a non-streaming ChatCompletionResponse.
    """
    full_text = ""
    full_thought = ""

    async for event in event_generator:
        if event.type == "error":
            full_text += f"\n[Error: {event.error}]"
            break
        if event.text:
            full_text = event.text
        elif event.delta:
            full_text += event.delta
        if event.thought:
            full_thought = event.thought
        elif event.thought_delta:
            full_thought += event.thought_delta
        if event.type == "done":
            break

    # Check for tool calls
    extracted_tools = SessionManager.extract_tool_calls(full_text, available_tool_names)
    if not extracted_tools and _is_transport_noise(full_text):
        full_text = ""
    tool_calls = None
    if extracted_tools:
        tool_calls = []
        for tc in extracted_tools:
            tool_calls.append(
                ToolCall(
                    function=FunctionCall(
                        name=tc["name"],
                        arguments=json.dumps(tc.get("arguments", {}), ensure_ascii=False) if isinstance(tc.get("arguments"), dict) else str(tc.get("arguments", "{}")),
                    )
                )
            )

    msg = ChatMessage(
        role="assistant",
        content=None if tool_calls else full_text,
        reasoning_content=full_thought if full_thought else None,
        tool_calls=tool_calls,
    )

    return ChatCompletionResponse(
        model=model,
        choices=[ChatCompletionResponseChoice(index=0, message=msg, finish_reason="tool_calls" if tool_calls else "stop")],
        usage={
            "prompt_tokens": len(full_text.split()) // 2,
            "completion_tokens": len(full_text.split()),
            "total_tokens": (len(full_text.split()) // 2) + len(full_text.split()),
        },
    )
