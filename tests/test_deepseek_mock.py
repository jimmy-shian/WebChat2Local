"""
Test DeepSeek Web Provider & OpenAI Compatibility
Simulates DeepSeek Web Client connecting via WebSocket and handles chat requests.
"""

import asyncio
import json
import sys
import httpx
import websockets

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

WS_URL = "ws://127.0.0.1:8765/ws"
API_BASE = "http://127.0.0.1:8765/v1"


async def mock_deepseek_browser():
    """Simulates DeepSeek Web tab with WebChat2Local extension loaded."""
    print("[DeepSeekMock] 正在連接本地伺服器 WebSocket...")
    async with websockets.connect(WS_URL) as ws:
        print("[DeepSeekMock] WebSocket 已連接！發送 DeepSeek 帳號資訊...")
        await ws.send(
            json.dumps({
                "type": "ready",
                "info": {
                    "email": "deepseek-user@deepseek.com",
                    "plan": "DeepSeek-V3 / R1 (Free Web)",
                    "provider": "DeepSeek",
                },
            })
        )

        while True:
            raw_msg = await ws.recv()
            data = json.loads(raw_msg)
            print(f"[DeepSeekMock] 收到任務: {data.get('type')} (req: {data.get('request_id')}, model: {data.get('model')})")

            if data.get("type") == "chat_request":
                req_id = data.get("request_id")
                model = data.get("model", "deepseek-chat")
                messages = data.get("messages", [])
                tools = data.get("tools", [])

                last_user_msg = messages[-1]["content"] if messages else "你好"

                if tools:
                    # Simulate tool call response from DeepSeek
                    simulated_response = (
                        "<read_file><path>test.txt</path></read_file>"
                    )
                else:
                    simulated_response = (
                        f"您好！我是 DeepSeek 網頁版模型 ({model})。\n"
                        f"已收到您的提問：『{last_user_msg}』。\n"
                        f"WebChat2Local 橋接與串流功能運作正常！"
                    )

                # Stream out chunk by chunk
                words = simulated_response.split(" ")
                accumulated = ""
                for w in words:
                    chunk = w + " "
                    accumulated += chunk
                    await ws.send(
                        json.dumps({
                            "type": "chunk",
                            "request_id": req_id,
                            "delta": chunk,
                            "accumulated": accumulated,
                        })
                    )
                    await asyncio.sleep(0.03)

                await ws.send(
                    json.dumps({
                        "type": "done",
                        "request_id": req_id,
                        "full_text": accumulated.strip(),
                        "finish_reason": "stop",
                    })
                )
                print(f"[DeepSeekMock] 任務 {req_id} 完成！")


async def run_client_tests():
    await asyncio.sleep(1.0)
    print("\n--- 1. 測試 GET /v1/models (確認包含 DeepSeek 模型) ---")
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/models")
        assert resp.status_code == 200, f"Status: {resp.status_code}"
        data = resp.json()
        model_ids = [m["id"] for m in data["data"]]
        print(f"✅ 成功獲取模型清單 (共 {len(model_ids)} 個):")
        for m in model_ids:
            print(f"   • {m}")
        assert "deepseek-chat" in model_ids, "deepseek-chat missing!"
        assert "deepseek-reasoner" in model_ids, "deepseek-reasoner missing!"

    print("\n--- 2. 測試 POST /v1/chat/completions (DeepSeek 即時串流 stream=True) ---")
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": "請以 DeepSeek 測試串流輸出"},
        ],
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("POST", f"{API_BASE}/chat/completions", json=payload) as resp:
            assert resp.status_code == 200, f"Status {resp.status_code}: {await resp.aread()}"
            print("🟢 收到 DeepSeek 串流回應:")
            print("--------------------------------------------------")
            chunks = []
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    print("\n--------------------------------------------------")
                    print("✅ 收到 [DONE] 串流結束標誌！")
                    break
                try:
                    parsed = json.loads(data_str)
                    delta = parsed["choices"][0]["delta"].get("content", "")
                    if delta:
                        sys.stdout.write(delta)
                        sys.stdout.flush()
                        chunks.append(delta)
                except Exception:
                    pass
            assert len(chunks) > 0, "No chunks received!"

    print("\n--- 3. 測試 DeepSeek 工具呼叫 (Tool Calling XML -> tool_calls) ---")
    payload_tool = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": "讀取檔案 test.txt"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read file",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                },
            }
        ],
        "stream": True,
    }
    tool_calls = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("POST", f"{API_BASE}/chat/completions", json=payload_tool) as resp:
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                parsed = json.loads(data_str)
                tc = parsed["choices"][0]["delta"].get("tool_calls")
                if tc:
                    tool_calls.extend(tc)

    assert len(tool_calls) > 0, "No tool_calls parsed!"
    print(f"✅ 工具呼叫解析成功: {tool_calls[0]['function']['name']} args={tool_calls[0]['function']['arguments']}")

    print("\n--- 4. 測試 POST /v1/chat/completions (DeepSeek 非串流 stream=False) ---")
    payload_non_stream = {
        "model": "deepseek-reasoner",
        "messages": [{"role": "user", "content": "DeepSeek R1 測試"}],
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{API_BASE}/chat/completions", json=payload_non_stream)
        assert resp.status_code == 200, f"Status: {resp.status_code}"
        data = resp.json()
        assert data["choices"][0]["message"]["content"], "Empty content!"
        print(f"✅ 非串流回應: {data['choices'][0]['message']['content'][:60]}...")

    print("\n🎉 DeepSeek 所有功能測試全部通過！")


async def main():
    server_task = asyncio.create_task(mock_deepseek_browser())
    client_task = asyncio.create_task(run_client_tests())

    done, pending = await asyncio.wait(
        [client_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    server_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
