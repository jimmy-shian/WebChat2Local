import json
import os
import subprocess
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import httpx

def test_cline_native_tool_calling():
    print("==================================================")
    print("🚀 [TEST CLINE NATIVE TOOL CALLING ADAPTER]")
    print("==================================================")

    # 1. Start Server
    server_proc = subprocess.Popen(
        [sys.executable, "run_server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8"
    )
    time.sleep(2)

    try:
        # Check health
        h = httpx.get("http://127.0.0.1:8765/health").json()
        print("Server Health:", h)

        # 2. Test Stream Adapter directly
        from server.stream_adapter import extract_tools_from_text, format_sse_chunk

        tools = [
            {"type": "function", "function": {"name": "attempt_completion", "description": "Complete task"}},
            {"type": "function", "function": {"name": "read_file", "description": "Read file"}},
        ]
        tool_names = ["attempt_completion", "read_file"]

        # Simulate user's exact response from Gemini / ChatGPT
        sample_response = """
你這個專案本質上是在做一個 **「Jimmy's Tools｜全方位實用線上工具庫」的個人 Web 工具網站**。

而 `index.html` 就是這個網站的**首頁／工具入口網站**。

## `index.html` 在做什麼？
1. 建立網站首頁
2. 載入整個網站共用的 UI
3. 分類 9 個工具（塔羅、計時器、生活實用工具）
        """.strip()

        tool_calls = extract_tools_from_text(sample_response, tool_names)
        print("\nExtracted Tool Calls:")
        print(json.dumps(tool_calls, indent=2, ensure_ascii=False))

        assert tool_calls is not None, "tool_calls must not be None"
        assert tool_calls[0]["function"]["name"] == "attempt_completion"
        args = json.loads(tool_calls[0]["function"]["arguments"])
        assert "result" in args, "Must contain 'result' parameter required by Cline"
        assert "Jimmy's Tools" in args["result"]

        # Test SSE chunk formatting with tool_calls
        chunk_sse = format_sse_chunk("req_123", "auto", tool_calls=tool_calls, finish_reason="tool_calls")
        print("\nGenerated SSE Chunk:")
        print(chunk_sse)

        assert '"tool_calls"' in chunk_sse
        assert '"finish_reason": "tool_calls"' in chunk_sse

        print("\n" + "="*50)
        print("🎉🎉🎉 [驗證成功] Cline 原生 Tool Calling 適配器 100% 完美通過！")
        print("Cline 絕不會再跳出 'MODEL_NO_TOOLS_USED' 或 'without value for result'！")
        print("="*50)

    finally:
        server_proc.terminate()
        server_proc.kill()

if __name__ == "__main__":
    test_cline_native_tool_calling()
