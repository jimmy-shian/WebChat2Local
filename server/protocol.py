"""
Protocol schemas and data structures for OpenAI Chat Completions,
Codex/Antigravity Responses API, and Browser WebSocket bridging.
"""

from typing import List, Dict, Any, Optional, Union, Literal
from pydantic import BaseModel, Field, ConfigDict
import time
import uuid


# ==========================================
# OpenAI Chat Completions Protocol Models
# ==========================================

class FunctionCall(BaseModel):
    name: str
    arguments: str


class ToolCall(BaseModel):
    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:12]}")
    type: Literal["function"] = "function"
    function: FunctionCall


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str  # "system", "user", "assistant", "tool", "developer"
    content: Optional[Union[str, List[Any], Dict[str, Any]]] = ""
    name: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = "gemini-web/pro"
    messages: List[ChatMessage]
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None


class ChatCompletionResponseChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = "stop"


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionResponseChoice]
    usage: Dict[str, int] = Field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0
    })


class ChatCompletionChunkDelta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class ChatCompletionChunkChoice(BaseModel):
    index: int = 0
    delta: ChatCompletionChunkDelta
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex}")
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChunkChoice]


# ==========================================
# Responses API (Codex/Antigravity) Models
# ==========================================

class ResponsesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = "gemini-web/pro"
    input: Union[str, List[Any], Dict[str, Any]]
    stream: Optional[bool] = True
    tools: Optional[List[Dict[str, Any]]] = None


# ==========================================
# WebSocket Bridge Protocols
# ==========================================

class WSIncomingMessage(BaseModel):
    type: str  # "ready", "chunk", "done", "error", "pong", "status"
    turn_id: Optional[str] = None
    text: Optional[str] = None
    delta: Optional[str] = None
    thought: Optional[str] = None
    thought_delta: Optional[str] = None
    is_generating: Optional[bool] = False
    error: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class WSOutgoingMessage(BaseModel):
    type: str  # "submit_prompt", "ping", "stop", "status_query"
    turn_id: Optional[str] = None
    prompt: Optional[str] = None
    model: Optional[str] = None
    options: Optional[Dict[str, Any]] = None
