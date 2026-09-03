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
    ) -> CompiledGeminiPrompt:
        """
        Returns the compiled text prompt used for the Gemini Web turn.
        When for_browser_session is True and the request is a continuation turn,
        compiles only the incremental continuation turn to be appended into the
        existing Gemini Web chat thread.
        """
        if for_browser_session and cls.is_continuation_turn(messages):
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
    def extract_tool_calls(
        text: str,
        available_tool_names: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        return GeminiPromptCompiler.extract_tool_calls(text, available_tool_names)
