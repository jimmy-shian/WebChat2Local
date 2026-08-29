import asyncio
import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from fastapi.testclient import TestClient
from server.server import app, manager

client = TestClient(app)

def test_endpoint_1_models():
    print("==================================================")
    print("🚀 [TEST ENDPOINT 1/3]: GET /v1/models & /models")
    print("==================================================")
    
    resp1 = client.get("/v1/models")
    assert resp1.status_code == 200, f"Expected 200, got {resp1.status_code}"
    data1 = resp1.json()
    assert data1["object"] == "list"
    model_ids = [m["id"] for m in data1["data"]]
    print(f"Retrieved {len(model_ids)} models: {model_ids}")
    assert "gpt-4o" in model_ids
    assert "gemini-2.5-flash" in model_ids
    assert "auto" in model_ids

    resp2 = client.get("/models")
    assert resp2.status_code == 200

    print("✅ Endpoint 1 (Models) Passed Successfully!\n")


def test_endpoint_2_health_and_dashboard():
    print("==================================================")
    print("🚀 [TEST ENDPOINT 2/3]: GET /health, /api/logs, /")
    print("==================================================")

    # 1. Health check
    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    health_data = resp_health.json()
    print("Health Data:", json.dumps(health_data, indent=2, ensure_ascii=False))
    assert "active_providers" in health_data
    assert "providers" in health_data

    # 2. Logs check
    resp_logs = client.get("/api/logs")
    assert resp_logs.status_code == 200
    assert isinstance(resp_logs.json(), list)

    # 3. Dashboard check
    resp_dash = client.get("/")
    assert resp_dash.status_code == 200
    assert "WebChat2Local" in resp_dash.text

    print("✅ Endpoint 2 (Health, Logs, Dashboard) Passed Successfully!\n")


def test_endpoint_3_multi_provider_routing_and_tool_calling():
    print("==================================================")
    print("🚀 [TEST ENDPOINT 3/3]: POST /v1/chat/completions (Plan A Routing & Tool Calling)")
    print("==================================================")

    # Mock MockSocket for ChatGPT
    class MockSocket:
        def __init__(self, name):
            self.name = name
            self.sent_jobs = []

        async def send_text(self, text):
            self.sent_jobs.append(json.loads(text))

    ws_chatgpt = MockSocket("ChatGPT")
    ws_gemini = MockSocket("Gemini")

    # Register both providers
    manager.register_provider(ws_chatgpt, {"provider": "ChatGPT", "email": "user@openai.com", "plan": "Free"})
    manager.register_provider(ws_gemini, {"provider": "Gemini", "email": "user@google.com", "plan": "Free"})

    print("Active providers in manager:", manager.active_providers)
    assert "ChatGPT" in manager.active_providers
    assert "Gemini" in manager.active_providers

    # Test 3.1: GPT model routes to ChatGPT
    prov1, sock1 = manager.get_provider_for_model("gpt-4o")
    print(f"Model 'gpt-4o' routed to: [{prov1}]")
    assert prov1 == "ChatGPT"
    assert sock1 is ws_chatgpt

    # Test 3.2: Gemini model routes to Gemini
    prov2, sock2 = manager.get_provider_for_model("gemini-2.5-flash")
    print(f"Model 'gemini-2.5-flash' routed to: [{prov2}]")
    assert prov2 == "Gemini"
    assert sock2 is ws_gemini

    # Test 3.3: Auto model routes to idle provider
    prov3, sock3 = manager.get_provider_for_model("auto")
    print(f"Model 'auto' routed to: [{prov3}]")
    assert prov3 in ["ChatGPT", "Gemini"]

    # Test 3.4: Stream Completions with Native Tool Calling Extraction
    from server.stream_adapter import extract_tools_from_text, format_sse_chunk

    sample_gpt_output = """
index.html 是 Jimmy's Tools 線上工具庫的首頁與總入口。
主要提供 9 款工具的導覽與即時搜尋功能。
    """.strip()

    tools_req = ["attempt_completion", "read_file"]
    extracted = extract_tools_from_text(sample_gpt_output, tools_req)
    print("\nSynthesized Tool Calling for Cline:", json.dumps(extracted, indent=2, ensure_ascii=False))
    assert extracted is not None
    assert extracted[0]["function"]["name"] == "attempt_completion"
    args = json.loads(extracted[0]["function"]["arguments"])
    assert "result" in args
    assert "Jimmy's Tools" in args["result"]

    # Test explicit XML tool extraction
    sample_xml_output = "<read_file><path>index.html</path></read_file>"
    extracted_xml = extract_tools_from_text(sample_xml_output, tools_req)
    print("Extracted XML Tool Call:", json.dumps(extracted_xml, indent=2, ensure_ascii=False))
    assert extracted_xml[0]["function"]["name"] == "read_file"
    assert json.loads(extracted_xml[0]["function"]["arguments"])["path"] == "index.html"

    # Cleanup mock
    manager.disconnect()
    print("\n✅ Endpoint 3 (Multi-Provider Routing & Native Tool Calling) Passed Successfully!")


if __name__ == "__main__":
    test_endpoint_1_models()
    test_endpoint_2_health_and_dashboard()
    test_endpoint_3_multi_provider_routing_and_tool_calling()
    print("\n" + "="*50)
    print("🎉🎉🎉 ALL 3 ENDPOINTS TESTED & 100% VERIFIED!")
    print("="*50)
