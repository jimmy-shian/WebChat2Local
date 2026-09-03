"""
Prompt Compiler for Gemini Web.
Ported and adapted from codex-chatgpt-web/src/adapters/chatgpt-web/prompt.ts.
Compiles client system prompts (Cline, Kilo, Antigravity, Cursor) and multi-turn
conversations into an optimized structure for Gemini Web with 100% fidelity.
"""

import json
import re
from typing import List, Dict, Any, Optional
from server.protocol import ChatMessage

# Regex for tool calls in assistant outputs
TOOL_CALL_REGEX = re.compile(
    r"<tool_call>\s*({.*?})\s*</tool_call>|```(?:json)?\s*<tool_call>\s*({.*?})\s*</tool_call>\s*```",
    re.DOTALL | re.IGNORECASE
)

# Regex for Cline / Roo Code tool call XML format
CLINE_TOOL_REGEX = re.compile(
    r"<([a-zA-Z0-9_-]+)>\s*(.*?)\s*</\1>",
    re.DOTALL
)


# Safe character ceiling for a single prompt submitted to Gemini Web.
# Gemini Web's batchexecute / RPC edge rejects requests above ~30k-35k chars with Error 1155.
# Keep a wide safety margin below the Web batchexecute/RPC request ceiling.
# This is a transport limit, not Gemini's model context window. CJK-heavy and
# tool-heavy prompts can consume substantially more tokens per character than
# the old 28k-character heuristic suggested.
GEMINI_WEB_MAX_PROMPT_CHARS = 16000


class CompiledGeminiPrompt:
    def __init__(self, text: str, estimated_tokens: int = 0):
        self.text = text
        self.estimated_tokens = estimated_tokens


class GeminiPromptCompiler:
    """
    Compiles OpenAI-style message arrays and tool definitions into structured Gemini Web prompts
    with automatic sliding-window compaction to respect Gemini Web's prompt budget.
    """

    @staticmethod
    def _extract_content_text(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content

        if isinstance(content, dict):
            return json.dumps(content, ensure_ascii=False)

        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict):
                    part_type = part.get("type", "text")
                    if part_type == "text":
                        text_parts.append(part.get("text", ""))
                    else:
                        # The bridge intentionally accepts text only.
                        text_parts.append(str(part.get("text", "")))
            return "\n".join(text_parts)

        return str(content)

    @classmethod
    def _compact_turns(
        cls,
        conversation_turns: List[str],
        base_overhead: int,
        max_budget: int = GEMINI_WEB_MAX_PROMPT_CHARS,
    ) -> List[str]:
        """
        Compacts conversation turns to fit comfortably within the Gemini Web character budget.
        Strategy:
        1. Strip all older <thought> blocks in past assistant turns.
        2. Compact large older <tool_result> blocks (> 1000 chars) by keeping head and tail.
        3. Sliding-window: keep the first turn (initial instruction) and most recent turns,
           compacting oldest middle turns.
        """
        available_budget = max_budget - base_overhead
        if available_budget <= 4000:
            available_budget = 4000

        current_total = sum(len(t) for t in conversation_turns)
        if current_total <= available_budget:
            return conversation_turns

        # Step 1: Strip thoughts and compact large tool results in non-final turns
        compacted: List[str] = []
        num_turns = len(conversation_turns)
        for i, turn in enumerate(conversation_turns):
            is_latest_turn = (i == num_turns - 1)
            # Remove old thought blocks in past assistant turns
            if not is_latest_turn and "<thought>" in turn:
                turn = re.sub(r"<thought>[\s\S]*?</thought>\s*", "", turn)

            # Compact oversized tool results in older turns
            if not is_latest_turn and "<tool_result" in turn and len(turn) > 1200:
                def _shrink_tool(match: re.Match) -> str:
                    header = match.group(1)
                    body = match.group(2)
                    if len(body) > 1000:
                        head = body[:500]
                        tail = body[-250:]
                        omitted = len(body) - 750
                        return f'{header}\n{head}\n... [tool result truncated: {omitted} chars omitted for Gemini Web length limit] ...\n{tail}\n</tool_result>'
                    return match.group(0)

                turn = re.sub(r'(<tool_result[^>]*>)([\s\S]*?)(</tool_result>)', _shrink_tool, turn)

            compacted.append(turn)

        current_total = sum(len(t) for t in compacted)
        if current_total <= available_budget:
            return compacted

        # Step 2: Sliding-window compaction if still over budget
        # Keep turn 0 (task root) and take turns from the end until budget is nearly filled
        if len(compacted) <= 2:
            # If only 1-2 turns, hard truncate the middle of turn 0
            t0 = compacted[0]
            if len(t0) > available_budget:
                compacted[0] = t0[:available_budget - 400] + "\n... [content truncated for Gemini Web length limit] ...\n</user>"
            return compacted

        first_turn = compacted[0]
        recent_turns: List[str] = []
        running_len = len(first_turn) + 200

        for turn in reversed(compacted[1:]):
            if running_len + len(turn) > available_budget:
                break
            recent_turns.insert(0, turn)
            running_len += len(turn)

        omitted_count = len(compacted) - 1 - len(recent_turns)
        if omitted_count > 0:
            marker = f"<history_compaction>[... {omitted_count} earlier turns compacted to stay within Gemini Web prompt limit ...]</history_compaction>"
            return [first_turn, marker] + recent_turns
        return [first_turn] + recent_turns

    @classmethod
    def compile(
        cls,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ) -> CompiledGeminiPrompt:
        """
        Compiles messages into a unified prompt string for Gemini Web.
        """
        if not messages:
            return CompiledGeminiPrompt(text="")

        system_prompts: List[str] = []
        if system_instruction:
            system_prompts.append(system_instruction.strip())

        # Gemini Web has no native awareness of the OpenAI tool protocol.
        if tools:
            tool_names = []
            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                fn = tool.get("function", tool)
                if isinstance(fn, dict) and fn.get("name"):
                    tool_names.append(str(fn["name"]))
            names = ", ".join(tool_names) if tool_names else "the supplied tools"
            system_prompts.append(
                "You are connected to a local coding client through a bridge. "
                "The host client owns and executes tools; you must never claim that "
                "you executed a local tool yourself. When a tool is needed, emit "
                "exactly one XML wrapper in this form and no Markdown around it: "
                '<tool_call>{"name":"TOOL_NAME","arguments":{}}</tool_call>. '
                f"Only call tools supplied by the host ({names}). Arguments must be valid JSON. "
                "After the host returns a tool result, continue the task using that result."
            )

        # If single user message with no extra metadata, pass directly
        if len(messages) == 1 and messages[0].role.lower() in ("user", "developer") and not tools and not system_instruction:
            text = cls._extract_content_text(messages[0].content)
            if len(text) > GEMINI_WEB_MAX_PROMPT_CHARS:
                text = text[:GEMINI_WEB_MAX_PROMPT_CHARS - 200] + "\n... [prompt truncated to fit Gemini Web limit]"
            return CompiledGeminiPrompt(text=text, estimated_tokens=len(text) // 4)

        conversation_turns: List[str] = []

        for msg in messages:
            role = (msg.role or "user").lower()
            text = cls._extract_content_text(msg.content)

            if role in ("system", "developer"):
                if text.strip():
                    system_prompts.append(text.strip())
            elif role == "user":
                conversation_turns.append(f"<user>\n{text}\n</user>")
            elif role == "assistant":
                asst_parts = []
                if msg.reasoning_content:
                    asst_parts.append(f"<thought>\n{msg.reasoning_content}\n</thought>")
                if text.strip():
                    asst_parts.append(text)
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        func_name = tc.function.name if hasattr(tc, "function") else tc.get("function", {}).get("name")
                        func_args = tc.function.arguments if hasattr(tc, "function") else tc.get("function", {}).get("arguments")
                        asst_parts.append(f'<tool_call>\n{{"name": "{func_name}", "arguments": {func_args}}}\n</tool_call>')

                asst_content = "\n".join(asst_parts)
                conversation_turns.append(f"<assistant>\n{asst_content}\n</assistant>")
            elif role == "tool":
                tool_name = msg.name or msg.tool_call_id or "tool"
                conversation_turns.append(f'<tool_result name="{tool_name}">\n{text}\n</tool_result>')

        # Construct final structured prompt blocks
        blocks: List[str] = []

        # 1. System instruction block
        if system_prompts:
            blocks.append("<system_instructions>")
            blocks.append("\n\n".join(system_prompts))
            blocks.append("</system_instructions>\n")

        # 2. Tools definition block
        if tools:
            blocks.append("<available_tools>")
            blocks.append(json.dumps(tools, ensure_ascii=False))
            blocks.append("</available_tools>\n")

        base_overhead = sum(len(b) for b in blocks) + 50

        # Apply intelligent turn compaction if total exceeds Gemini Web budget
        final_turns = cls._compact_turns(
            conversation_turns=conversation_turns,
            base_overhead=base_overhead,
            max_budget=GEMINI_WEB_MAX_PROMPT_CHARS,
        )

        # 3. Conversation turns
        if final_turns:
            blocks.append("\n\n".join(final_turns))

        final_text = "\n\n".join(blocks)
        return CompiledGeminiPrompt(
            text=final_text,
            estimated_tokens=len(final_text) // 4
        )

    @classmethod
    def extract_tool_calls(cls, text: str, available_tool_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Extracts tool calls from generated text.
        Supports:
        1. JSON Decoder / Balanced Parser for <tool_call>...</tool_call> (handles nested XML/code safely)
        2. TOOL_CALL_REGEX fallback
        3. Cline / Roo-Code direct XML tags (<read_file><path>...</path></read_file>)
        """
        calls = []
        decoder = json.JSONDecoder()

        # Strategy 1: JSONDecoder raw_decode starting after each <tool_call> tag
        pos = 0
        while pos < len(text):
            idx = text.find("<tool_call>", pos)
            if idx == -1:
                # Also check markdown blocks with <tool_call>
                idx = text.find("```json\n<tool_call>", pos)
                if idx == -1:
                    idx = text.find("```<tool_call>", pos)
                    if idx == -1:
                        break
                    start_json = idx + len("```<tool_call>")
                else:
                    start_json = idx + len("```json\n<tool_call>")
            else:
                start_json = idx + len("<tool_call>")

            while start_json < len(text) and text[start_json].isspace():
                start_json += 1

            if start_json >= len(text):
                break

            # Try raw_decode from start_json
            try:
                parsed, end_idx = decoder.raw_decode(text, start_json)
                if isinstance(parsed, dict) and "name" in parsed:
                    calls.append({
                        "name": str(parsed["name"]),
                        "arguments": parsed.get("arguments", {}),
                        "raw_match": text[idx:end_idx],
                    })
                    pos = end_idx
                    continue
            except Exception:
                pass

            pos = start_json + 1

        # Strategy 2: Fallback to regex if raw_decode found nothing
        if not calls:
            for match in TOOL_CALL_REGEX.finditer(text):
                raw_json = match.group(1) or match.group(2)
                if raw_json:
                    try:
                        parsed = json.loads(raw_json.strip())
                        if isinstance(parsed, dict) and "name" in parsed:
                            calls.append({
                                "name": str(parsed["name"]),
                                "arguments": parsed.get("arguments", {}),
                                "raw_match": match.group(0),
                            })
                    except Exception:
                        pass

        # Strategy 3: Accept Cline / Roo Code direct XML tags
        if not calls and available_tool_names:
            for tool_name in available_tool_names:
                safe_name = re.escape(tool_name)
                pattern = re.compile(rf"<{safe_name}(?:\s+[^>]*)?>(.*?)</{safe_name}>", re.DOTALL | re.IGNORECASE)
                for match in pattern.finditer(text):
                    inner = match.group(1).strip()
                    args: Dict[str, Any] = {}
                    params = re.findall(r"<([a-zA-Z0-9_-]+)>(.*?)</\1>", inner, re.DOTALL)
                    if params:
                        args.update({key: value.strip() for key, value in params})
                    elif inner:
                        if tool_name in ("attempt_completion",):
                            args["result"] = inner
                        elif tool_name in ("read_file", "write_to_file", "edit_file"):
                            args["path"] = inner
                        elif tool_name in ("execute_command", "run_command"):
                            args["command"] = inner
                        else:
                            args["content"] = inner
                    calls.append({"name": tool_name, "arguments": args, "raw_match": match.group(0)})

        return calls
