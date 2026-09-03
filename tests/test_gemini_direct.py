import json

from server.browser.gemini_direct import _extract_text_from_chunk


def _frame(response):
    payload = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
    record = [["wrb.fr", None, payload]]
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def test_extracts_model_text_from_double_encoded_wrb_frame():
    response = [
        None,
        ["c_test", "r_test"],
        None,
        None,
        [
            ["rc_test", ["GEMINI_DIRECT_OK"], None],
            ["location", ["Taiwan Changhua City"], None],
            None,
            None,
            "3.7 Flash",
            True,
            [[[1004, "Longer"], [1001, "Try again"], [1003, "Personalize"]]],
        ],
    ]
    assert _extract_text_from_chunk(_frame(response)) == "GEMINI_DIRECT_OK"


def test_ignores_ui_metadata_when_no_response_chunk_is_available():
    response = [
        None,
        ["c_test", "r_test"],
        None,
        None,
        [
            ["location", ["Taiwan Changhua City"], None],
            ["ui", ["Personalize"], None],
            None,
            None,
            "3.7 Flash",
        ],
    ]
    assert _extract_text_from_chunk(_frame(response)) == ""


def test_extracts_tool_call_from_raw_stream():
    raw = '<tool_call>\n{"name": "execute_command", "arguments": {"command": "ls"}}\n</tool_call>'
    assert _extract_text_from_chunk(raw) == raw


def test_extracts_streaming_tool_call_without_closing_tag():
    raw = '<tool_call>\n{"name": "execute_command", "arguments": {"command": "ls"}}'
    assert _extract_text_from_chunk(raw) == raw


def test_json_lines_frames_are_parsed():
    from server.browser.gemini_direct import _extract_stream_frames
    line1 = json.dumps(["wrb.fr", None, "{}"])
    line2 = json.dumps(["wrb.fr", None, "{}"])
    roots = list(_extract_stream_frames(line1 + "\n" + line2))
    assert len(roots) == 2
    assert roots[0][0] == "wrb.fr"
    assert roots[1][0] == "wrb.fr"
