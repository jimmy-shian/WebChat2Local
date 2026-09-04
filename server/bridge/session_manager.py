"""
Session Manager and Multi-turn Context Hub for Gemini Web.
Ensures 100% preservation of client system prompts (Cline, Kilo, Antigravity)
and seamless multi-turn conversation tracking.
"""

from typing import List, Dict, Any, Optional
from server.protocol import ChatMessage
from server.bridge.prompt_compiler import GeminiPromptCompiler, CompiledGeminiPrompt


class SessionManager:
    """
    Manages prompt compilation and context lifecycle.
    """

    @classmethod
    def is_continuation_turn(cls, messages: List[ChatMessage]) -> bool:
        """
        Determines if the current request represents a continuation of an ongoing conversation
        (e.g. tool result return or multi-turn follow-up) rather than a brand-new task.
        """
        if not messages or len(messages) < 2:
            return False
        has_prior_assistant = any((m.role or "").lower() == "assistant" for m in messages[:-1])
        last_is_tool_or_user = (messages[-1].role or "").lower() in ("tool", "function", "user")
        return has_prior_assistant and last_is_tool_or_user

    @classmethod
    def compile_prompt(
        cls,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        enable_mcp_system: bool = False,
        system_instruction: Optional[str] = None,
    ) -> str:
        """
        Compiles messages into a structured prompt string for Gemini Web.
        """
        compiled = GeminiPromptCompiler.compile(
            messages=messages,
            tools=tools,
            system_instruction=system_instruction,
        )
        return compiled.text

    @classmethod
    def compile_rich_prompt(
        cls,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
        for_browser_session: bool = False,
        for_stateful_session: bool = False,
    ) -> CompiledGeminiPrompt:
        """
        Returns the compiled text prompt used for the Gemini Web turn.
        When for_browser_session or for_stateful_session is True and the request is a
        continuation turn, compiles only the incremental continuation turn to be
        appended into the existing Gemini Web chat thread.
        """
        is_stateful = for_browser_session or for_stateful_session
        if is_stateful and cls.is_continuation_turn(messages):
            return GeminiPromptCompiler.compile_continuation_turn(
                messages=messages,
                tools=tools,
            )
        return GeminiPromptCompiler.compile(
            messages=messages,
            tools=tools,
            system_instruction=system_instruction,
        )

    @staticmethod
    def get_conversation_fingerprint(messages: List[ChatMessage]) -> str:
        """
        Extracts a stable conversation fingerprint across multi-turn requests
        from the initial user task and system instructions.
        """
        import hashlib
        if not messages:
            return "session_empty"

        sys_parts = []
        user_parts = []
        for m in messages:
            role = (m.role or "").lower()
            content_str = str(m.content or "")
            if role in ("system", "developer") and not sys_parts:
                sys_parts.append(content_str[:500])
            elif role == "user" and not user_parts:
                user_parts.append(content_str[:1000])

        raw_key = f"{''.join(sys_parts)}||{''.join(user_parts)}"
        if not raw_key.strip(" |"):
            raw_key = str(messages[0].content or "")[:500]

        return hashlib.sha256(raw_key.encode("utf-8", errors="ignore")).hexdigest()[:16]

    @staticmethod
    def extract_tool_calls(
        text: str,
        available_tool_names: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        return GeminiPromptCompiler.extract_tool_calls(text, available_tool_names)

