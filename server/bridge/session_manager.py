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
    ) -> CompiledGeminiPrompt:
        """Returns the compiled text prompt used for the Gemini Web turn."""
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
