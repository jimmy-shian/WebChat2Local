import json
import os
import subprocess
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

EXTENSION_PATH = os.path.abspath(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension")

def test_live_chatgpt_e2e():
    print("==================================================")
    print("🚀 [LIVE E2E TEST: CHATGPT WEB -> CLINE API BRIDGE]")
    print("==================================================")

    # 1. Start Server Process
    print("\n[Step 1] Starting local server...")
    server_proc = subprocess.Popen(
        [sys.executable, "run_server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8"
    )
    time.sleep(3)

    # 2. Start Chrome with extension loaded
    print("[Step 2] Launching Chrome with WebChat2Local extension...")
    options = Options()
    options.add_argument(f"--load-extension={EXTENSION_PATH}")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)

    try:
        # Navigate to ChatGPT
        print("[Step 3] Opening https://chatgpt.com...")
        driver.get("https://chatgpt.com")
        time.sleep(6)

        # Verify extension connected in server health
        health = httpx.get("http://127.0.0.1:8765/health", timeout=5.0).json()
        print("Server Health & Active Providers:", json.dumps(health, indent=2, ensure_ascii=False))
        assert health["browser_connected"], "Browser extension must be connected"
        assert "ChatGPT" in health["active_providers"], "ChatGPT provider must be active"

        # 4. Send API request from client (simulating Cline/Kilo Code)
        print("\n[Step 4] Sending Cline-style API request to /v1/chat/completions (model: gpt-4o)...")
        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "system",
                    "content": "You are Cline, an AI coding assistant. You have tools to read and complete tasks. Follow strict format."
                },
                {
                    "role": "user",
                    "content": "請告訴我：index.html 是什麼檔案？我的專案包含哪三大類工具？請用條列簡短回答。"
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "attempt_completion",
                        "description": "Report completion of task",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "result": {"type": "string"}
                            },
                            "required": ["result"]
                        }
                    }
                }
            ],
            "stream": True
        }

        with httpx.Client(timeout=90.0) as client:
            resp = client.post("http://127.0.0.1:8765/v1/chat/completions", json=payload)
            print("HTTP Status:", resp.status_code)
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

            sse_lines = resp.text.split("\n")
            received_chunks = []
            final_tool_calls = None

            for line in sse_lines:
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        chunk_json = json.loads(line[6:])
                        choices = chunk_json.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            if delta.get("content"):
                                received_chunks.append(delta["content"])
                            if delta.get("tool_calls"):
                                final_tool_calls = delta["tool_calls"]
                    except Exception:
                        pass

            full_text = "".join(received_chunks)
            print("\n[Step 5] Received Streaming Response Full Text:\n" + full_text[:400] + "...")
            print("\n[Step 6] Final Tool Calls Received by Client:")
            print(json.dumps(final_tool_calls, indent=2, ensure_ascii=False))

            assert len(full_text) > 0, "Response must not be empty"
            assert final_tool_calls is not None, "Client must receive tool_calls for Cline"
            assert final_tool_calls[0]["function"]["name"] == "attempt_completion"
            args = json.loads(final_tool_calls[0]["function"]["arguments"])
            assert "result" in args, "'result' parameter must be present"

            print("\n" + "="*50)
            print("🎉🎉🎉 [VERIFIED LIVE]: ChatGPT Web successfully executed the task, streamed the response,")
            print("and Cline received 100% valid attempt_completion(result=...)!")
            print("="*50)

    finally:
        driver.quit()
        server_proc.terminate()
        server_proc.kill()

if __name__ == "__main__":
    test_live_chatgpt_e2e()
