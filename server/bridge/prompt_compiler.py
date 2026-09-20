"""
Prompt Compiler for Gemini Web.
Ported and adapted from codex-chatgpt-web/src/adapters/chatgpt-web/prompt.ts.
Compiles client system prompts (Cline, Kilo, Antigravity, Cursor) and multi-turn
conversations into an optimized structure for Gemini Web with 100% fidelity.
"""

import hashlib
import json
import logging
import os
import re
from typing import List, Dict, Any, Optional
from server.protocol import ChatMessage

LOGGER = logging.getLogger("webchat2local.bridge")


# Spillover staging directory for large outputs (> 12,000 characters, such as 100k git diffs)
SPILLOVER_DIR = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "scratch", "spillover")


def spill_or_compact_tool_result(text: str, tool_name: str = "", max_inline_chars: int = 12000) -> str:
    """
    If a tool result exceeds max_inline_chars (e.g. 111k git diff or huge test logs),
    saves full content to a local spillover file, extracts a clean structural file
    summary (e.g. git status file list and diff headers), and returns a safe inline
    preview (< 5000 chars) with the file path.
    """
    if len(text) <= max_inline_chars:
        return text

    file_path = ""
    try:
        os.makedirs(SPILLOVER_DIR, exist_ok=True)
        content_hash = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()[:10]
        file_name = f"tool_{tool_name or 'output'}_{content_hash}_{len(text)}.txt"
        file_path = os.path.join(SPILLOVER_DIR, file_name)
        with open(file_path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(text)
    except Exception as e:
        file_path = f"(failed to write spillover file: {e})"

    # Structural extraction for git status / git diff
    lines = text.splitlines()
    status_lines = []
    diff_file_headers = []

    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(k) for k in [
            "On branch", "Changes to be committed:", "Changes not staged for commit:",
            "Untracked files:", "modified:", "new file:", "deleted:", "renamed:"
        ]):
            status_lines.append(line)
        elif line.startswith("diff --git "):
            diff_file_headers.append(line)

    summary_parts = []
    if status_lines:
        summary_parts.append("=== Git Status Summary ===")
        summary_parts.append("\n".join(status_lines[:60]))
    if diff_file_headers:
        summary_parts.append("\n=== Modified Files in Diff ===")
        summary_parts.append("\n".join(diff_file_headers[:60]))

    if summary_parts:
        summary_text = "\n".join(summary_parts)
    else:
        # Fallback for non-git massive logs (e.g. test output)
        summary_text = text[:4000] + "\n...\n" + text[-1000:]

    return (
        f"{summary_text}\n\n"
        f"[⚠️ 完整工具輸出共 {len(text):,} 字元，已自動存入本地暫存檔案：{file_path}]\n"
        f"[說明：為避免超出瀏覽器訊息上限，已為您整理上述變更檔案清單。若需檢視特定檔案的詳細變更，請呼叫 read_file 或專用指令檢視。]"
    )


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
# Gemini Web RPC starts rejecting or timing out when prompt exceeds ~35,000 characters.
# Setting safe threshold to 32,000 chars ensures instant, error-free responses.
GEMINI_WEB_MAX_PROMPT_CHARS = 32000



STANDARD_CODING_TOOLS = [
    "execute_command", "run_command", "bash", "terminal",
    "read_file", "write_to_file", "edit_file", "apply_diff",
    "list_files", "list_dir", "search_files", "grep_search", "find_by_name",
    "list_code_definition_names", "update_todo_list", "todo_list", "manage_todo",
    "browser_action", "use_mcp_tool", "access_mcp_resource",
    "ask_followup_question", "ask_question", "ask_user",
    "attempt_completion", "new_task", "switch_mode",
    "fetch_web_page", "view_file"
]


class CompiledGeminiPrompt:
    def __init__(self, text: str, estimated_tokens: int = 0, is_continuation: bool = False):
        self.text = text
        self.estimated_tokens = estimated_tokens
        self.is_continuation = is_continuation


class GeminiPromptCompiler:
    """
    Compiles OpenAI-style message arrays and tool definitions into structured Gemini Web prompts
    with automatic sliding-window compaction to respect Gemini Web's prompt budget.
    """

    @classmethod
    def _extract_content_text(cls, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content

        if isinstance(content, dict):
            if "type" in content:
                part_type = content.get("type", "")
                if part_type == "text":
                    return str(content.get("text", ""))
                elif part_type == "tool_use":
                    tool_name = content.get("name", "")
                    tool_args = content.get("input", content.get("arguments", {}))
                    tool_id = content.get("id", "")
                    args_json = json.dumps(tool_args, ensure_ascii=False) if isinstance(tool_args, (dict, list)) else str(tool_args)
                    return cls._fmt_tool_call_block(tool_name, args_json, tool_id)
                elif part_type == "tool_result":
                    res = content.get("content") or content.get("output") or content.get("result") or content.get("text") or ""
                    if isinstance(res, list):
                        res = "\n".join(cls._extract_content_text(p) for p in res)
                    tool_id = content.get("tool_use_id", content.get("id", ""))
                    compacted_res = spill_or_compact_tool_result(str(res))
                    return cls._fmt_tool_result_block("", tool_id, compacted_res)
                elif part_type in ("image_url", "image"):
                    return "[Image]"

            if "text" in content:
                return str(content["text"])
            if "content" in content:
                return cls._extract_content_text(content["content"])
            if "output" in content:
                return str(content["output"])
            if "result" in content:
                return str(content["result"])
            return json.dumps(content, ensure_ascii=False)

        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict):
                    part_type = part.get("type", "")
                    if part_type == "text":
                        text_parts.append(str(part.get("text", "")))
                    elif part_type == "tool_use":
                        tool_name = part.get("name", "")
                        tool_args = part.get("input", part.get("arguments", {}))
                        tool_id = part.get("id", "")
                        args_json = json.dumps(tool_args, ensure_ascii=False) if isinstance(tool_args, (dict, list)) else str(tool_args)
                        text_parts.append(cls._fmt_tool_call_block(tool_name, args_json, tool_id))
                    elif part_type == "tool_result":
                        res = part.get("content") or part.get("output") or part.get("result") or part.get("text") or ""
                        if isinstance(res, list):
                            res = "\n".join(cls._extract_content_text(p) for p in res)
                        tool_id = part.get("tool_use_id", part.get("id", ""))
                        text_parts.append(cls._fmt_tool_result_block("", tool_id, str(res)))
                    elif part_type in ("image_url", "image"):
                        text_parts.append("[Image]")
                    elif "text" in part:
                        text_parts.append(str(part.get("text", "")))
                    elif "content" in part:
                        text_parts.append(cls._extract_content_text(part.get("content", "")))
                    elif "output" in part:
                        text_parts.append(str(part.get("output", "")))
                    elif "result" in part:
                        text_parts.append(str(part.get("result", "")))
                    else:
                        text_parts.append(json.dumps(part, ensure_ascii=False))
                else:
                    text_parts.append(str(part))
            return "\n".join(text_parts)

        return str(content)

    # Plain-text markers for Gemini Web single-textbox prompts.
    # No angle-bracket XML tags are emitted here; parsing side (extract_tool_calls)
    # intentionally keeps accepting legacy <tool_call>/<tool_result> for compat.
    TOOL_CALL_HEADER = "Assistant tool call"
    TOOL_RESULT_HEADER = "Tool result"
    TOOL_RESULT_END = "[end of tool result]"
    THINKING_START = "[thinking]"
    THINKING_END = "[/thinking]"

    @classmethod
    def _fmt_tool_call_block(cls, name: str, args_json: str, call_id: str = "") -> str:
        header = cls.TOOL_CALL_HEADER
        if call_id:
            header += f' [id="{call_id}"]'
        header += ":"
        return f'{header}\n```json\n{{"name": "{name}", "arguments": {args_json}}}\n```'

    @classmethod
    def _fmt_tool_result_block(cls, name: str = "", call_id: str = "", body: str = "") -> str:
        header = cls.TOOL_RESULT_HEADER
        attrs = []
        if name:
            attrs.append(f'tool="{name}"')
        if call_id:
            attrs.append(f'id="{call_id}"')
        if attrs:
            header += " [" + " ".join(attrs) + "]"
        header += ":"
        return f"{header}\n{body}\n{cls.TOOL_RESULT_END}"

    @classmethod
    def _has_tool_content(cls, turn: str) -> bool:
        return (
            "```json" in turn
            or cls.TOOL_RESULT_HEADER in turn
            or cls.TOOL_RESULT_END in turn
            # legacy compat: old prompts / Gemini outputs may still carry XML tags
            or "<tool_call" in turn
            or "<tool_result" in turn
        )

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
        1. Strip older thinking blocks in past assistant turns.
        2. Compact large older tool result blocks (> 1000 chars) by keeping head and tail.
        3. Sliding-window: keep the first turn (initial instruction) and most recent turns,
           compacting oldest middle turns.
        Plain-text markers are used; legacy <thought>/<tool_result> tags are
        still handled for backwards compatibility.
        """
        available_budget = max_budget - base_overhead
        if available_budget <= 4000:
            available_budget = 4000

        current_total = sum(len(t) for t in conversation_turns)
        if current_total <= available_budget:
            return conversation_turns

        # Step 1: Strip thoughts and compact large tool results
        compacted: List[str] = []
        num_turns = len(conversation_turns)
        for i, turn in enumerate(conversation_turns):
            is_latest_turn = (i == num_turns - 1)
            # Remove old thinking blocks in past assistant turns (new + legacy)
            if not is_latest_turn:
                if cls.THINKING_START in turn:
                    turn = re.sub(
                        r"\[thinking\][\s\S]*?\[/thinking\]\s*",
                        "",
                        turn,
                    )
                if "<thought>" in turn:
                    turn = re.sub(r"<thought>[\s\S]*?</thought>\s*", "", turn)

            # Compact oversized tool results (new plain-text marker)
            limit = 6000 if is_latest_turn else 1000
            if cls.TOOL_RESULT_HEADER in turn and len(turn) > (limit + 200):
                def _shrink_plain_tool(match: re.Match) -> str:
                    header = match.group(1)
                    body = match.group(2)
                    end = match.group(3)
                    if len(body) > limit:
                        head_len = limit // 2
                        tail_len = limit // 4
                        head = body[:head_len]
                        tail = body[-tail_len:]
                        omitted = len(body) - head_len - tail_len
                        return f'{header}\n{head}\n... [tool result truncated: {omitted} chars omitted for Gemini Web length limit] ...\n{tail}\n{end}'
                    return match.group(0)

                turn = re.sub(
                    r"(Tool result[^\n]*:\n)([\s\S]*?)(\n\[end of tool result\])",
                    _shrink_plain_tool,
                    turn,
                )
            # Legacy compat: old <tool_result> blocks
            if "<tool_result" in turn and len(turn) > (limit + 200):
                def _shrink_tool(match: re.Match) -> str:
                    header = match.group(1)
                    body = match.group(2)
                    if len(body) > limit:
                        head_len = limit // 2
                        tail_len = limit // 4
                        head = body[:head_len]
                        tail = body[-tail_len:]
                        omitted = len(body) - head_len - tail_len
                        return f'{header}\n{head}\n... [tool result truncated: {omitted} chars omitted for Gemini Web length limit] ...\n{tail}\n</tool_result>'
                    return match.group(0)

                turn = re.sub(r'(<tool_result[^>]*>)([\s\S]*?)(</tool_result>)', _shrink_tool, turn)

            compacted.append(turn)

        current_total = sum(len(t) for t in compacted)
        if current_total <= available_budget:
            return compacted

        # Step 2: Ensure budget is reserved for recent turns (including tool results)
        # Kilo/Cline often sends a massive 40KB+ system prompt in turn 0.
        # We allow up to 26k chars for first_turn while guaranteeing at least 16k chars for recent turns.
        max_first_turn_len = min(26000, max(12000, available_budget - 16000))
        first_turn = compacted[0]
        if len(compacted) > 1 and len(first_turn) > max_first_turn_len:
            head_len = max_first_turn_len // 2
            tail_len = max_first_turn_len // 2
            first_turn = (
                first_turn[:head_len]
                + "\n... [system instructions compacted to prioritize recent context and tool results] ...\n"
                + first_turn[-tail_len:]
            )

        recent_budget = available_budget - len(first_turn) - 300
        recent_turns: List[str] = []
        running_len = 0

        for turn in reversed(compacted[1:]):
            if running_len + len(turn) > recent_budget:
                if not recent_turns:
                    # Guarantee at least the very latest turn is partially included
                    turn_shrunk = turn[:max(500, recent_budget - running_len - 100)] + "\n... [latest turn truncated to fit] ..."
                    recent_turns.insert(0, turn_shrunk)
                break
            recent_turns.insert(0, turn)
            running_len += len(turn)

        omitted_count = len(compacted) - 1 - len(recent_turns)
        if omitted_count > 0:
            marker = f"[... {omitted_count} earlier turns compacted to stay within Gemini Web prompt limit ...]"
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

        # Deduplicate repeating client error loops (e.g. Kilo/Cline repeating MODEL_NO_TOOLS_USED)
        cleaned_messages: List[ChatMessage] = []
        last_was_tool_error = False
        for msg in messages:
            content_str = str(msg.content or "")
            is_tool_error = "[ERROR] You did not use a tool in your previous response!" in content_str
            if is_tool_error:
                if last_was_tool_error:
                    continue
                last_was_tool_error = True
            else:
                last_was_tool_error = False
            cleaned_messages.append(msg)

        system_prompts: List[str] = []
        if system_instruction:
            system_prompts.append(system_instruction.strip())

        # Gemini Web tool calling directive
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
                "CRITICAL SYSTEM DIRECTIVE - LOCAL WORKSPACE TOOL ACCESS:\n"
                "You are an autonomous AI coding assistant running with direct access to the user's local workspace.\n"
                f"You have the following tools available to inspect and modify the project: {names}.\n"
                "NEVER refuse requests by saying you cannot access local files, have no environment, or lack MCP support.\n"
                "Whenever the user asks you to read, search, create, edit files, list directories, or run commands, "
                "you MUST immediately invoke the appropriate tool.\n\n"
                "To call a tool, output exactly one JSON code block:\n"
                '```json\n{"name": "TOOL_NAME", "arguments": {"PARAM": "VALUE"}}\n```\n'
                "Arguments must be valid JSON matching the tool's parameter schema.\n"
                "The host client will execute the tool locally on the user's machine and return the output as a Tool result message.\n"
                "When you receive a Tool result, inspect the output and proceed to answer the user's request or call another tool."
            )

        # If single user message with no extra metadata, pass directly
        if len(messages) == 1 and messages[0].role.lower() in ("user", "developer") and not tools and not system_instruction:
            text = cls._extract_content_text(messages[0].content)
            if len(text) > GEMINI_WEB_MAX_PROMPT_CHARS:
                text = text[:GEMINI_WEB_MAX_PROMPT_CHARS - 200] + "\n... [prompt truncated to fit Gemini Web limit]"
            return CompiledGeminiPrompt(text=text, estimated_tokens=len(text) // 4)

        conversation_turns: List[str] = []

        for msg in cleaned_messages:
            role = (msg.role or "user").lower()
            text = cls._extract_content_text(msg.content)

            if role in ("system", "developer"):
                if text.strip():
                    system_prompts.append(text.strip())
            elif role == "user":
                conversation_turns.append(f"User:\n{text}")
            elif role == "assistant":
                asst_parts = []
                if msg.reasoning_content:
                    asst_parts.append(f"{cls.THINKING_START}\n{msg.reasoning_content}\n{cls.THINKING_END}")
                if text.strip():
                    asst_parts.append(text)
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        if isinstance(tc, dict):
                            fn = tc.get("function", {})
                            func_name = fn.get("name", "") if isinstance(fn, dict) else str(tc.get("name", ""))
                            func_args = fn.get("arguments", {}) if isinstance(fn, dict) else tc.get("arguments", {})
                            call_id = tc.get("id", "")
                        else:
                            func_name = getattr(tc.function, "name", "")
                            func_args = getattr(tc.function, "arguments", {})
                            call_id = getattr(tc, "id", "")

                        if isinstance(func_args, str):
                            try:
                                parsed_args = json.loads(func_args)
                                args_json = json.dumps(parsed_args, ensure_ascii=False)
                            except Exception:
                                args_json = func_args
                        else:
                            args_json = json.dumps(func_args, ensure_ascii=False)

                        asst_parts.append(cls._fmt_tool_call_block(func_name, args_json, call_id or ""))

                asst_content = "\n".join(asst_parts)
                conversation_turns.append(f"Assistant:\n{asst_content}")
            elif role in ("tool", "function"):
                tool_name = msg.name or ""
                call_id = msg.tool_call_id or ""
                compacted_text = spill_or_compact_tool_result(text, tool_name=tool_name)
                conversation_turns.append(cls._fmt_tool_result_block(tool_name, call_id, compacted_text))

        # If the conversation ends with a tool result, prompt the assistant to take the turn
        if cleaned_messages and (cleaned_messages[-1].role or "").lower() in ("tool", "function"):
            conversation_turns.append(
                "The previous tool execution has completed with the Tool result above.\n"
                "- Review the result and proceed with answering the user's task or calling the next tool (e.g. `read_file`, `execute_command`).\n"
                "- Do NOT stop or call `attempt_completion` prematurely after merely listing files or taking initial steps."
            )


        # Construct final structured prompt blocks
        blocks: List[str] = []

        # 1. System instruction block (plain text, no XML wrapper)
        if system_prompts:
            blocks.append("\n\n".join(system_prompts))

        # 2. Tools definition block
        if tools:
            blocks.append("Available tools:\n" + cls._compact_tools_definition(tools))

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

        # 4. Mandatory action directive when tools are available
        action_prompt = ""
        if tools or any(cls._has_tool_content(turn) for turn in conversation_turns):
            action_prompt = (
                "CRITICAL INSTRUCTION FOR THIS TURN:\n"
                "You are an autonomous AI coding agent operating directly in the workspace.\n"
                "- NEVER guess or invent file contents or changes from filenames alone.\n"
                "- If you have not inspected the actual code diff or file contents yet, you MUST call `execute_command` (e.g. `git diff`) or `read_file` FIRST before writing any final answer.\n"
                "- To execute a tool, output brief reasoning (optional), then output your tool call as one JSON code block:\n"
                '```json\n{"name": "TOOL_NAME", "arguments": {"PARAM": "VALUE"}}\n```\n'
                "- ONLY call `attempt_completion` when you have thoroughly verified all actual file contents/diffs and completely solved the user's task.\n"
                "NEVER give conversational excuses. Always emit a tool call JSON block."
            )
            blocks.append(action_prompt)

        final_text = "\n\n".join(blocks)

        # Hard ceiling enforcement: ensure total prompt NEVER exceeds GEMINI_WEB_MAX_PROMPT_CHARS
        if len(final_text) > GEMINI_WEB_MAX_PROMPT_CHARS:
            LOGGER.warning("⚠️ [PROMPT COMPILER] Prompt 長度 (%d) 超過上限 (%d)，進行保護性裁切...", len(final_text), GEMINI_WEB_MAX_PROMPT_CHARS)
            if system_prompts and len("\n\n".join(system_prompts)) > 14000:
                joined_sys = "\n\n".join(system_prompts)
                keep_head = joined_sys[:10000]
                keep_tail = joined_sys[-3000:]
                trimmed_sys = keep_head + "\n\n... [system instructions trimmed for web budget] ...\n\n" + keep_tail
                if blocks and system_prompts:
                    blocks[0] = trimmed_sys
                final_text = "\n\n".join(blocks)
            if len(final_text) > GEMINI_WEB_MAX_PROMPT_CHARS:
                final_text = final_text[:GEMINI_WEB_MAX_PROMPT_CHARS - 350] + "\n\n... [context truncated to fit web budget]\n\n" + action_prompt

        return CompiledGeminiPrompt(
            text=final_text,
            estimated_tokens=len(final_text) // 4,
            is_continuation=False,
        )

    @staticmethod
    def _compact_tools_definition(tools: List[Dict[str, Any]]) -> str:
        """
        Serializes tools into a compact, clean format without massive 2-space indentation,
        trimming verbose descriptions to keep the prompt well within Google Gemini Web limits.
        """
        compact_list = []
        for t in tools:
            if not isinstance(t, dict):
                continue
            fn = t.get("function", t) if isinstance(t.get("function"), dict) else t
            name = fn.get("name", "")
            desc = (fn.get("description", "") or "").strip()
            if "\n\n" in desc:
                desc = desc.split("\n\n")[0].strip()
            if len(desc) > 200:
                desc = desc[:200] + "..."

            params = fn.get("parameters", {})
            props = params.get("properties", {}) if isinstance(params, dict) else {}
            compact_props = {}
            for p_name, p_def in props.items():
                if isinstance(p_def, dict):
                    p_type = p_def.get("type", "string")
                    p_desc = (p_def.get("description", "") or "").strip()
                    if len(p_desc) > 80:
                        p_desc = p_desc[:80] + "..."
                    entry = {"type": p_type}
                    if p_desc:
                        entry["description"] = p_desc
                    if "enum" in p_def:
                        entry["enum"] = p_def["enum"]
                    compact_props[p_name] = entry
                else:
                    compact_props[p_name] = p_def

            compact_fn = {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": compact_props,
                }
            }
            if isinstance(params, dict) and "required" in params:
                compact_fn["parameters"]["required"] = params["required"]
            compact_list.append(compact_fn)

        return json.dumps(compact_list, ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def compile_continuation_turn(
        cls,

        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> CompiledGeminiPrompt:
        """
        Compiles ONLY the latest incremental continuation turn (e.g. recent tool_result)
        to be appended directly into an existing active Gemini Web thread, without re-sending
        past conversation turns.
        """
        if not messages:
            return CompiledGeminiPrompt(text="", is_continuation=True)

        # Find the last message or sequence of messages after the last assistant turn
        last_asst_idx = -1
        for i, m in enumerate(messages):
            if (m.role or "").lower() == "assistant":
                last_asst_idx = i

        if last_asst_idx >= 0 and last_asst_idx < len(messages) - 1:
            recent_messages = messages[last_asst_idx + 1:]
        else:
            recent_messages = [messages[-1]]

        parts: List[str] = []
        for msg in recent_messages:
            role = (msg.role or "user").lower()
            text = cls._extract_content_text(msg.content)
            if role in ("tool", "function"):
                tool_name = msg.name or ""
                call_id = msg.tool_call_id or ""
                compacted_text = spill_or_compact_tool_result(text, tool_name=tool_name)
                parts.append(cls._fmt_tool_result_block(tool_name, call_id, compacted_text))
            elif role == "user":
                parts.append(f"User:\n{text}")

        if not parts:
            parts.append("Proceed with the next step.")
        else:
            parts.append(
                "You are actively working on the user's task. Review the latest Tool result above.\n"
                "- Do NOT terminate or give up after just listing directories or inspecting partial data.\n"
                "- Continue with the next necessary action (e.g. `read_file` to inspect code, `execute_command`, or answering the user's task in full).\n"
                "- To invoke a tool, output exactly one JSON code block:\n"
                '```json\n{"name": "TOOL_NAME", "arguments": {"PARAM": "VALUE"}}\n```\n'
                "- ONLY call `attempt_completion` when you have thoroughly completed all requirements of the user's task."
            )


        text = "\n\n".join(parts)
        return CompiledGeminiPrompt(text=text, estimated_tokens=len(text) // 4, is_continuation=True)

    @classmethod
    def _sanitize_and_repair_gemini_artifacts(cls, text: str) -> str:
        """
        Repairs Google Gemini Web specific token splits, grounding artifacts,
        and malformed JSON openings (e.g. 'Google Searchname": ...').
        """
        if not text:
            return ""
        t = text

        # 1. Repair "Google Searchname": "..." or "Google Search" corruptions
        t = re.sub(r'Google\s*Search\s*name"\s*:', '<tool_call>{"name":', t, flags=re.IGNORECASE)
        t = re.sub(r'Google\s*Search\s*"name"\s*:', '<tool_call>{"name":', t, flags=re.IGNORECASE)
        t = re.sub(r'Google\s*Search\s*tool"\s*:', '<tool_call>{"tool":', t, flags=re.IGNORECASE)
        t = re.sub(r'Google\s*Search\s*"tool"\s*:', '<tool_call>{"tool":', t, flags=re.IGNORECASE)
        t = re.sub(r'Google\s*Search\s*command"\s*:', '<tool_call>{"command":', t, flags=re.IGNORECASE)
        t = re.sub(r'Google\s*Search\s*"command"\s*:', '<tool_call>{"command":', t, flags=re.IGNORECASE)
        t = re.sub(r'Google\s*Search\s*path"\s*:', '<tool_call>{"path":', t, flags=re.IGNORECASE)
        t = re.sub(r'Google\s*Search\s*"path"\s*:', '<tool_call>{"path":', t, flags=re.IGNORECASE)

        # 2. Strip standalone "Google Search" or search grounding citations
        t = re.sub(r'^(?:Google\s*Search\s*)+', '', t.strip(), flags=re.IGNORECASE)
        t = re.sub(r'^(?:Searched(?:\s+for)?\s*:?[^\n]*\n?)+', '', t.strip(), flags=re.IGNORECASE)

        # 3. Repair missing leading bracket inside <tool_call>
        # e.g. <tool_call>name": "execute_command"... -> <tool_call>{"name": "execute_command"...
        t = re.sub(r'(<tool_call[^>]*>\s*)(?:\{)?\s*name"\s*:', r'\1{"name":', t, flags=re.IGNORECASE)
        t = re.sub(r'(<tool_call[^>]*>\s*)(?:\{)?\s*"name"\s*:', r'\1{"name":', t, flags=re.IGNORECASE)
        t = re.sub(r'(<tool_call[^>]*>\s*)(?:\{)?\s*tool"\s*:', r'\1{"tool":', t, flags=re.IGNORECASE)
        t = re.sub(r'(<tool_call[^>]*>\s*)(?:\{)?\s*"tool"\s*:', r'\1{"tool":', t, flags=re.IGNORECASE)
        t = re.sub(r'(<tool_call[^>]*>\s*)(?:\{)?\s*command"\s*:', r'\1{"command":', t, flags=re.IGNORECASE)
        t = re.sub(r'(<tool_call[^>]*>\s*)(?:\{)?\s*"command"\s*:', r'\1{"command":', t, flags=re.IGNORECASE)
        t = re.sub(r'(<tool_call[^>]*>\s*)(?:\{)?\s*path"\s*:', r'\1{"path":', t, flags=re.IGNORECASE)
        t = re.sub(r'(<tool_call[^>]*>\s*)(?:\{)?\s*"path"\s*:', r'\1{"path":', t, flags=re.IGNORECASE)

        # 4. Repair standalone malformed JSON if string starts directly with name": or "name":
        t = re.sub(r'^\s*name"\s*:', '<tool_call>{"name":', t, flags=re.IGNORECASE)
        t = re.sub(r'^\s*"name"\s*:', '<tool_call>{"name":', t, flags=re.IGNORECASE)

        return t

    @classmethod
    def extract_tool_calls(cls, text: str, available_tool_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Extracts tool calls from generated text.
        Supports:
        1. Google Gemini Web token-split & search-grounding repaired payloads
        2. JSONDecoder / Balanced Parser for <tool_call>...</tool_call> (handles nested XML/code safely)
        3. Direct parameter JSON / inference
        4. TOOL_CALL_REGEX fallback
        5. Markdown code blocks with JSON tool calls
        6. Python / tool_code function execution blocks (````tool_code ...````)
        7. ReAct Action / Action Input syntax
        8. Cline / Roo-Code direct XML tags (<read_file><path>...</path></read_file>)
        """
        calls = []
        decoder = json.JSONDecoder()

        # Step 0: Pre-sanitize Google-specific grounding artifacts and malformed openings
        text = cls._sanitize_and_repair_gemini_artifacts(text)

        # Strategy 1: JSONDecoder raw_decode starting after each <tool_call> tag
        pos = 0
        while pos < len(text):
            idx = text.find("<tool_call>", pos)
            if idx == -1:
                # Also check markdown blocks with <tool_call> or <tool_call name="...">
                idx = text.find("```json\n<tool_call>", pos)
                if idx == -1:
                    idx = text.find("```<tool_call>", pos)
                    if idx == -1:
                        # Check <tool_call name="...">
                        m = re.search(r'<tool_call(?:\s+name="([^"]+)")?>', text[pos:])
                        if m:
                            idx = pos + m.start()
                            start_json = idx + len(m.group(0))
                        else:
                            break
                    else:
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
                if isinstance(parsed, dict):
                    if "name" in parsed or "tool" in parsed:
                        t_name = str(parsed.get("name") or parsed.get("tool"))
                        t_args = parsed.get("arguments", parsed.get("parameters", parsed.get("input", {})))
                        calls.append({
                            "name": t_name,
                            "arguments": t_args if isinstance(t_args, (dict, list)) else (t_args if t_args else {}),
                            "raw_match": text[idx:end_idx],
                        })
                        pos = end_idx
                        continue
                    elif "command" in parsed:
                        calls.append({
                            "name": "execute_command",
                            "arguments": parsed,
                            "raw_match": text[idx:end_idx],
                        })
                        pos = end_idx
                        continue
                    elif "todos" in parsed or "todo_list" in parsed:
                        t_name = "update_todo_list" if "update_todo_list" in (available_tool_names or []) else ("todo_list" if "todo_list" in (available_tool_names or []) else "update_todo_list")
                        calls.append({
                            "name": t_name,
                            "arguments": parsed,
                            "raw_match": text[idx:end_idx],
                        })
                        pos = end_idx
                        continue
                    elif "question" in parsed or "questions" in parsed:
                        t_name = "ask_question" if "ask_question" in (available_tool_names or []) else "ask_followup_question"
                        calls.append({
                            "name": t_name,
                            "arguments": parsed,
                            "raw_match": text[idx:end_idx],
                        })
                        pos = end_idx
                        continue
                    elif "recursive" in parsed:
                        calls.append({
                            "name": "list_files",
                            "arguments": parsed,
                            "raw_match": text[idx:end_idx],
                        })
                        pos = end_idx
                        continue
                    elif "path" in parsed:
                        if "content" in parsed or "file_text" in parsed:
                            t_name = "write_to_file"
                        elif "list_files" in (available_tool_names or []):
                            t_name = "list_files"
                        elif "list_code_definition_names" in (available_tool_names or []):
                            t_name = "list_code_definition_names"
                        else:
                            t_name = "read_file"
                        calls.append({
                            "name": t_name,
                            "arguments": parsed,
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
                        if isinstance(parsed, dict):
                            if "name" in parsed or "tool" in parsed:
                                t_name = str(parsed.get("name") or parsed.get("tool"))
                                t_args = parsed.get("arguments", parsed.get("parameters", parsed.get("input", {})))
                                calls.append({
                                    "name": t_name,
                                    "arguments": t_args if isinstance(t_args, (dict, list)) else (t_args if t_args else {}),
                                    "raw_match": match.group(0),
                                })
                            elif "command" in parsed:
                                calls.append({
                                    "name": "execute_command",
                                    "arguments": parsed,
                                    "raw_match": match.group(0),
                                })
                            elif "todos" in parsed or "todo_list" in parsed:
                                calls.append({
                                    "name": "update_todo_list",
                                    "arguments": parsed,
                                    "raw_match": match.group(0),
                                })
                            elif "question" in parsed or "questions" in parsed:
                                t_name = "ask_question" if "ask_question" in (available_tool_names or []) else "ask_followup_question"
                                calls.append({
                                    "name": t_name,
                                    "arguments": parsed,
                                    "raw_match": match.group(0),
                                })
                    except Exception:
                        pass

        # Strategy 3: Check for JSON code block containing tool/function call
        if not calls:
            code_block_match = re.search(r'```(?:json)?\s*(\{\s*"(?:name|tool|function|tool_calls|command|todos|question)"[\s\S]*?\})\s*```', text)
            if code_block_match:
                try:
                    parsed = json.loads(code_block_match.group(1).strip())
                    if isinstance(parsed, dict):
                        if "name" in parsed or "tool" in parsed:
                            t_name = str(parsed.get("name") or parsed.get("tool"))
                            t_args = parsed.get("arguments", parsed.get("parameters", parsed.get("input", {})))
                            calls.append({
                                "name": t_name,
                                "arguments": t_args if isinstance(t_args, (dict, list)) else (t_args if t_args else {}),
                                "raw_match": code_block_match.group(0),
                            })
                        elif "tool_calls" in parsed and isinstance(parsed["tool_calls"], list):
                            for tc in parsed["tool_calls"]:
                                if isinstance(tc, dict) and "name" in tc:
                                    t_name = str(tc["name"])
                                    t_args = tc.get("arguments", tc.get("parameters", {}))
                                    calls.append({
                                        "name": t_name,
                                        "arguments": t_args if isinstance(t_args, (dict, list)) else (t_args if t_args else {}),
                                        "raw_match": code_block_match.group(0),
                                    })
                        elif "command" in parsed:
                            calls.append({
                                "name": "execute_command",
                                "arguments": parsed,
                                "raw_match": code_block_match.group(0),
                            })
                        elif "todos" in parsed or "todo_list" in parsed:
                            calls.append({
                                "name": "update_todo_list",
                                "arguments": parsed,
                                "raw_match": code_block_match.group(0),
                            })
                        elif "question" in parsed or "questions" in parsed:
                            t_name = "ask_question" if "ask_question" in (available_tool_names or []) else "ask_followup_question"
                            calls.append({
                                "name": t_name,
                                "arguments": parsed,
                                "raw_match": code_block_match.group(0),
                            })
                except Exception:
                    pass

        # Strategy 4: Accept Cline / Roo Code direct XML tags
        if not calls:
            all_target_tools = list(available_tool_names or [])
            for st in STANDARD_CODING_TOOLS:
                if st not in all_target_tools:
                    all_target_tools.append(st)

            for tool_name in all_target_tools:
                safe_name = re.escape(tool_name)
                pattern = re.compile(rf"<{safe_name}(?:\s+[^>]*)?>(.*?)</{safe_name}>", re.DOTALL | re.IGNORECASE)
                for match in pattern.finditer(text):
                    inner = match.group(1).strip()
                    args: Dict[str, Any] = {}
                    params = re.findall(r"<([a-zA-Z0-9_-]+)>(.*?)</\1>", inner, re.DOTALL)
                    if params:
                        for key, value in params:
                            k = key.strip()
                            v = value.strip()
                            if v.startswith(("[", "{")) and v.endswith(("]", "}")):
                                try:
                                    args[k] = json.loads(v)
                                    continue
                                except Exception:
                                    pass
                            if k == "options" and "<option>" in v:
                                opt_list = re.findall(r"<option>(.*?)</option>", v, re.DOTALL)
                                if opt_list:
                                    args[k] = [o.strip() for o in opt_list]
                                    continue
                            if k == "recursive":
                                args[k] = v.lower() in ("true", "1", "yes")
                                continue
                            args[k] = v
                    elif inner:
                        if inner.startswith(("[", "{")) and inner.endswith(("]", "}")):
                            try:
                                parsed_inner = json.loads(inner)
                                if tool_name in ("update_todo_list", "todo_list", "manage_todo"):
                                    args["todos"] = parsed_inner if isinstance(parsed_inner, list) else parsed_inner.get("todos", parsed_inner)
                                elif isinstance(parsed_inner, dict):
                                    args.update(parsed_inner)
                                else:
                                    args["content"] = parsed_inner
                            except Exception:
                                pass
                        if not args:
                            if tool_name in ("attempt_completion",):
                                args["result"] = inner
                            elif tool_name in ("ask_followup_question", "ask_question", "ask_user"):
                                args["question"] = inner
                            elif tool_name in ("list_files", "list_dir"):
                                args["path"] = inner or "."
                                args["recursive"] = False
                            elif tool_name in ("list_code_definition_names",):
                                args["path"] = inner
                            elif tool_name in ("update_todo_list", "todo_list", "manage_todo"):
                                args["todos"] = inner
                            elif tool_name in ("read_file", "write_to_file", "edit_file", "view_file"):
                                args["path"] = inner
                            elif tool_name in ("execute_command", "run_command", "bash", "terminal"):
                                args["command"] = inner
                            else:
                                args["content"] = inner
                    calls.append({"name": tool_name, "arguments": args, "raw_match": match.group(0)})

        # Strategy 5: Accept Python function call or tool_code block syntax
        if not calls:
            code_fn_match = re.search(r'```(?:tool_code|python)?\s*([a-zA-Z0-9_]+)\s*\(([\s\S]*?)\)\s*```', text)
            if code_fn_match:
                fn_name = code_fn_match.group(1)
                fn_args_raw = code_fn_match.group(2).strip()
                args: Dict[str, Any] = {}
                for kw_m in re.finditer(r'([a-zA-Z0-9_]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s,)]+))', fn_args_raw):
                    k = kw_m.group(1)
                    v = kw_m.group(2) if kw_m.group(2) is not None else (kw_m.group(3) if kw_m.group(3) is not None else kw_m.group(4))
                    args[k] = v
                if not args and fn_args_raw.startswith(('"', "'")):
                    val = fn_args_raw.strip("\"'")
                    if fn_name in ("execute_command", "run_command", "bash"):
                        args["command"] = val
                    elif fn_name in ("read_file", "view_file", "write_to_file", "edit_file"):
                        args["path"] = val
                    else:
                        args["input"] = val
                if fn_name in STANDARD_CODING_TOOLS or (available_tool_names and fn_name in available_tool_names):
                    calls.append({"name": fn_name, "arguments": args, "raw_match": code_fn_match.group(0)})

        # Strategy 6: ReAct Action / Action Input syntax
        if not calls:
            react_match = re.search(r'Action:\s*([a-zA-Z0-9_]+)\s*\n+\s*Action Input:\s*(\{[\s\S]*?\}|[^\n]+)', text, re.IGNORECASE)
            if react_match:
                action_name = react_match.group(1).strip()
                action_input_raw = react_match.group(2).strip()
                args: Dict[str, Any] = {}
                try:
                    args = json.loads(action_input_raw)
                except Exception:
                    if action_name in ("execute_command", "run_command", "bash"):
                        args = {"command": action_input_raw}
                    elif action_name in ("read_file", "view_file"):
                        args = {"path": action_input_raw}
                    else:
                        args = {"input": action_input_raw}
                if action_name in STANDARD_CODING_TOOLS or (available_tool_names and action_name in available_tool_names):
                    calls.append({"name": action_name, "arguments": args, "raw_match": react_match.group(0)})

        return calls
