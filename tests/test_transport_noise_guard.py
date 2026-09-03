from server.bridge.stream_adapter import _is_transport_noise


def test_google_map_url_is_transport_noise():
    assert _is_transport_noise("//www.google.com/maps/vt/data=opaque-token")


def test_normal_text_is_not_transport_noise():
    assert not _is_transport_noise("E2E_OK: Gemini response received.")


def test_opaque_identifier_is_transport_noise():
    assert _is_transport_noise("AbCdEf0123456789_xYz")
    assert _is_transport_noise("af.httprm")
    assert _is_transport_noise("wrb.fr")


def test_google_maps_opaque_path_without_scheme_is_transport_noise():
    assert _is_transport_noise(
        "//www.google.com/maps/vt/data=-4cG2I2qGg3hmnAYvwxJvNjx7n3QEHx5pVUS_G2gTo20-OGUXEXMzgeee_MTo5OQnUXbaAJar7lhgYMqzcrxnuKVDSeAvRv5TtY8viCuqEOnzrbC-KqM6CqtxL-sEcWuxzHlh3m15Cs"
    )


def test_geolocation_metadata_is_transport_noise():
    assert _is_transport_noise("台灣彰化縣彰化市下廍里")
    assert _is_transport_noise("台灣台北市信義區")
    assert _is_transport_noise("根據您的 IP 位址 - 依據您的位置")
    assert not _is_transport_noise("已完成 Markdown 說明文件整合與測試檔案分類規劃。以下為整理成果與對應結構：\n\n一、 Markdown 說明文件整合方案")
import asyncio
import json

from server.bridge.stream_adapter import stream_openai_completions
from server.bridge.ws_hub import TurnEvent


async def _events():
    yield TurnEvent("delta", text="<tool_", delta="<tool_")
    yield TurnEvent("delta", text='<tool_call>{"name":"read_file","arguments":{"path":"docs"}}</tool_call>', delta='call>{"name":"read_file","arguments":{"path":"docs"}}</tool_call>')
    yield TurnEvent("done", text='<tool_call>{"name":"read_file","arguments":{"path":"docs"}}</tool_call>')


def test_split_tool_marker_is_not_leaked_as_text():
    async def collect():
        return [line async for line in stream_openai_completions(_events(), available_tool_names=["read_file"])]

    lines = asyncio.run(collect())
    payloads = [json.loads(x[6:]) for x in lines if x.startswith("data: {")]
    content = "".join(
        p["choices"][0]["delta"].get("content", "")
        for p in payloads
    )
    assert "<tool_" not in content
    tool_chunks = [p for p in payloads if p["choices"][0]["delta"].get("tool_calls")]
    assert tool_chunks
    assert tool_chunks[0]["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == "read_file"
