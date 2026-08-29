"""
Live end-to-end test: sends a real tool-calling request through the running
WebChat2Local server and prints the raw response for diagnosis.

Usage: python tests/live_tool_call_test.py
"""
import io
import json
import sys

import httpx

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = "http://127.0.0.1:8765/v1"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Execute a CLI command on the user's machine",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to execute"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "attempt_completion",
            "description": "Present the final result of the task",
            "parameters": {
                "type": "object",
                "properties": {
                    "result": {"type": "string", "description": "The final result description"},
                },
                "required": ["result"],
            },
        },
    },
]


def main():
    payload = {
        "model": "gpt-4o",
        "stream": True,
        "messages": [
            {
                "role": "user",
                "content": '你幫我新建一個 "new.txt" 檔案，裡面文字寫 "Hello World"',
            }
        ],
        "tools": TOOLS,
    }

    print("=== 發送請求 ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:500])
    print()

    full_text = []
    tool_calls = []
    finish_reason = None

    with httpx.Client(timeout=200.0) as client:
        with client.stream("POST", f"{BASE}/chat/completions", json=payload) as resp:
            print(f"HTTP {resp.status_code}")
            if resp.status_code != 200:
                print(resp.read().decode("utf-8", errors="replace"))
                sys.exit(1)

            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    print("\n[DONE]")
                    break
                try:
                    chunk = json.loads(data)
                except Exception:
                    continue
                choice = chunk["choices"][0]
                delta = choice.get("delta", {})
                if delta.get("content"):
                    full_text.append(delta["content"])
                    sys.stdout.write(delta["content"])
                    sys.stdout.flush()
                if delta.get("tool_calls"):
                    for tc in delta["tool_calls"]:
                        tool_calls.append(tc)
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]

    raw = "".join(full_text)
    print("\n\n=== 診斷 ===")
    print(f"finish_reason: {finish_reason}")
    print(f"content 長度: {len(raw)}")
    print(f"content 原文:\n{raw}")
    print(f"tool_calls 數量: {len(tool_calls)}")
    for tc in tool_calls:
        print(f"  - {tc.get('function', {}).get('name')}: {tc.get('function', {}).get('arguments')}")

    has_xml = "<execute_command>" in raw or "<attempt_completion>" in raw
    print(f"\n回覆含 XML 工具標籤: {has_xml}")
    print(f"回覆含純文字說明(失敗徵兆): {'請' in raw and '執行' in raw and not has_xml}")


if __name__ == "__main__":
    main()