"""
End-to-End OpenAI-Compatible API Test Script
Tests /v1/models and /v1/chat/completions (streaming and non-streaming)
"""

import json
import sys
import httpx

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


BASE_URL = "http://127.0.0.1:8765/v1"


def test_models_list():
    print("\n--- 1. 測試 GET /v1/models ---")
    with httpx.Client() as client:
        resp = client.get(f"{BASE_URL}/models")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        print(f"✅ 成功獲取模型列表，共 {len(data['data'])} 個模型:")
        for m in data["data"]:
            print(f"   • {m['id']}")


def test_chat_completions_streaming():
    print("\n--- 2. 測試 POST /v1/chat/completions (即時串流 stream=True) ---")
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "You are a helpful coding assistant."},
            {"role": "user", "content": "請寫一個質數判斷函數並解釋。"},
        ],
        "stream": True,
    }

    full_response = []
    with httpx.Client(timeout=30.0) as client:
        with client.stream("POST", f"{BASE_URL}/chat/completions", json=payload) as resp:
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            print("🟢 收到串流回應 (即時輸出打字效果):")
            print("--------------------------------------------------")
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data_content = line[6:]
                    if data_content == "[DONE]":
                        print("\n--------------------------------------------------")
                        print("✅ 收到 [DONE] 串流結束標誌！")
                        break
                    try:
                        chunk = json.loads(data_content)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            sys.stdout.write(delta)
                            sys.stdout.flush()
                            full_response.append(delta)
                    except Exception as e:
                        print(f"Error parsing chunk: {e}")

    assert len(full_response) > 0, "No content received in stream!"
    print(f"✅ 串流測試成功！總字數: {len(''.join(full_response))}")


def test_cline_tool_calling():
    print("\n--- 3. 測試 Cline 工具呼叫 (XML 標籤 -> OpenAI tool_calls) ---")
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "請讀取 index.html"},
        ],
        "stream": True,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "attempt_completion",
                    "description": "Complete the task",
                    "parameters": {
                        "type": "object",
                        "properties": {"result": {"type": "string"}},
                    },
                },
            },
        ],
    }

    tool_calls_received = []
    finish_reason = None
    with httpx.Client(timeout=60.0) as client:
        with client.stream("POST", f"{BASE_URL}/chat/completions", json=payload) as resp:
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_content = line[6:]
                if data_content == "[DONE]":
                    break
                chunk = json.loads(data_content)
                choice = chunk["choices"][0]
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
                delta = choice.get("delta", {})
                if delta.get("tool_calls"):
                    for tc in delta["tool_calls"]:
                        # OpenAI spec: streamed tool_calls MUST carry an index field
                        assert "index" in tc, f"Streamed tool_call missing 'index': {tc}"
                        tool_calls_received.append(tc)

    assert tool_calls_received, "No tool_calls received from stream!"
    first = tool_calls_received[0]
    assert first["function"]["name"] in ("read_file", "attempt_completion")
    args = json.loads(first["function"]["arguments"])
    print(f"✅ 工具呼叫解析成功: {first['function']['name']} args={args}")
    print(f"✅ finish_reason = {finish_reason}")


def test_chat_completions_non_streaming():
    print("\n--- 4. 測試 POST /v1/chat/completions (非串流 stream=False) ---")
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "1 + 1 等於多少？"},
        ],
        "stream": False,
    }

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{BASE_URL}/chat/completions", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        print("✅ 成功獲取非串流 JSON 回應:")
        print(f"   ID: {data.get('id')}")
        print(f"   Model: {data.get('model')}")
        print(f"   Content:\n{data['choices'][0]['message']['content']}")


if __name__ == "__main__":
    print("==================================================")
    print("🧪 開始執行 WebChat2Local OpenAI API 規格相容性測試")
    print("==================================================")
    try:
        test_models_list()
        test_chat_completions_streaming()
        test_cline_tool_calling()
        test_chat_completions_non_streaming()
        print("\n🎉 全部 API 測試通過！完美符合 OpenAI 規格！")
    except Exception as err:
        print(f"\n❌ 測試失敗: {err}")
        sys.exit(1)
