"""
Mock Browser Client for Automated Testing
Simulates the WebChat2Local browser extension on ChatGPT Web.
"""

import asyncio
import json
import sys
import websockets

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


async def run_mock_browser(ws_url: str = "ws://127.0.0.1:8765/ws"):
    print(f"[MockBrowser] Connecting to bridge at {ws_url}...")
    async with websockets.connect(ws_url) as ws:
        print("[MockBrowser] Connected! Sending 'ready' payload...")
        await ws.send(
            json.dumps({
                "type": "ready",
                "info": {
                    "email": "test-user@chatgpt.web",
                    "plan": "ChatGPT Plus (Mock)",
                },
            })
        )

        while True:
            raw_msg = await ws.recv()
            data = json.loads(raw_msg)
            print(f"[MockBrowser] Received job: {data.get('type')} (req: {data.get('request_id')})")

            if data.get("type") == "chat_request":
                req_id = data.get("request_id")
                model = data.get("model", "gpt-4o")
                messages = data.get("messages", [])

                last_user_msg = messages[-1]["content"] if messages else "No content"
                simulated_response = (
                    f"哈囉！這是由 WebChat2Local 橋接的 ChatGPT 網頁版回應。\n"
                    f"收到您的提問：『{last_user_msg}』。\n"
                    f"目前正在使用模型：{model}。\n"
                    f"以下為您示範 Python 代碼：\n\n"
                    f"```python\ndef is_prime(n):\n    if n < 2: return False\n    for i in range(2, int(n**0.5)+1):\n        if n % i == 0: return False\n    return True\n```\n"
                    f"串流測試完成！"
                )

                # Stream out character by character or word by word
                words = simulated_response.split(" ")
                accumulated = ""
                for word in words:
                    chunk = word + " "
                    accumulated += chunk
                    await ws.send(
                        json.dumps({
                            "type": "chunk",
                            "request_id": req_id,
                            "delta": chunk,
                            "accumulated": accumulated,
                        })
                    )
                    await asyncio.sleep(0.04)

                # Send done
                await ws.send(
                    json.dumps({
                        "type": "done",
                        "request_id": req_id,
                        "full_text": accumulated,
                        "finish_reason": "stop",
                    })
                )
                print(f"[MockBrowser] Completed job {req_id}")


if __name__ == "__main__":
    asyncio.run(run_mock_browser())
