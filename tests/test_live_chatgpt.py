import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

EXTENSION_PATH = os.path.abspath(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension")

def test_live_chatgpt():
    print("==================================================")
    print("🚀 [LIVE E2E TEST: CHATGPT WEB -> CLINE API BRIDGE]")
    print("==================================================")

    # 1. Launch Chrome with extension loaded
    print("[Step 1] Launching Chrome with WebChat2Local extension...")
    options = Options()
    options.add_argument(f"--load-extension={EXTENSION_PATH}")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)

    try:
        # Navigate to ChatGPT
        print("[Step 2] Opening https://chatgpt.com...")
        driver.get("https://chatgpt.com")
        
        # Wait up to 15s for WebSocket connection
        print("[Step 3] Waiting for extension WebSocket handshake...")
        connected = False
        for i in range(15):
            time.sleep(1)
            try:
                health = httpx.get("http://127.0.0.1:8765/health", timeout=3.0).json()
                if health.get("browser_connected"):
                    print(f"[{i+1}s] Connected! Active Providers:", health.get("active_providers"))
                    connected = True
                    break
            except Exception:
                pass
            print(f"[{i+1}s] Waiting for extension connection...")

        assert connected, "Extension did not connect to server within 15s"

        # 4. Send API request from client (simulating Cline/Kilo Code)
        print("\n[Step 4] Sending Cline-style API request to /v1/chat/completions (model: gpt-4o)...")
        payload = {
            "model": "gpt-4o",
            "messages": [
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
            print("and Cline received 100% valid attempt_completion(result=...) without MODEL_NO_TOOLS_USED!")
            print("="*50)

    finally:
        driver.quit()

if __name__ == "__main__":
    test_live_chatgpt()
