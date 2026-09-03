"""
Direct Gemini Web client using Google account cookies (__Secure-1PSID).

This module bypasses the browser extension entirely by calling Gemini's
internal StreamGenerate RPC directly over HTTPS. It is the "cookie / access id"
path the user asked for: you supply your Google session cookies and the bridge
talks to gemini.google.com without needing a Chrome/Edge tab open.

Cookie sources (checked in order):
  1. Environment variables GEMINI_1PSID / GEMINI_1PSIDTS
  2. A JSON file at <workspace>/gemini_cookies.json with keys "1psid" / "1psidts"
  3. Auto-fetch from local Edge/Chrome profile (Playwright, handles App-Bound Encryption)

Security note: these cookies are equivalent to your logged-in Google session.
Keep them out of version control (the project .gitignore already excludes
credential-like files; add gemini_cookies.json if it is not already ignored).
"""

import os
import re
import json
import asyncio
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional, Dict, Any

import httpx

from server.bridge.ws_hub import TurnEvent
from server.config import get_workspace_root
from server.browser.cookie_auto import auto_fetch_cookies

# Gemini internal RPC endpoint (BardFrontendService.StreamGenerate).
STREAM_GENERATE_URL = (
    "https://gemini.google.com/_/BardChatUi/data/"
    "assistant.lamda.BardFrontendService/StreamGenerate"
)

# The "bl" (build label) query parameter changes with each Gemini frontend
# release. We fetch it dynamically from the app HTML so the request stays valid.
_BL_RE = re.compile(r'"boq_assistant-bard-web-server_[^"]+"')
_AT_RE = re.compile(r'"SNlM0e":"([^"]+)"')
_BL_RE_CURRENT = re.compile(r'"cfb2h":"([^"]+)"')
_SID_RE = re.compile(r'"FdrFJe":"([^"]+)"')

# A plausible browser User-Agent. Gemini rejects requests that look like bots.
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class GeminiDirectError(Exception):
    """Raised when the direct Gemini client cannot proceed."""


def _cookie_file() -> Path:
    return get_workspace_root() / "gemini_cookies.json"


def save_cookies(one_psid: str, one_psidts: str = "") -> bool:
    """
    Persist the __Secure-1PSID / __Secure-1PSIDTS cookies to gemini_cookies.json.
    Returns True on success.
    """
    try:
        data = {"1psid": one_psid.strip(), "1psidts": one_psidts.strip()}
        _cookie_file().write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
    except OSError:
        return False


def load_cookies() -> Dict[str, str]:
    """
    Resolve the __Secure-1PSID / __Secure-1PSIDTS cookies.

    Sources (checked in order):
      1. Environment variables GEMINI_1PSID / GEMINI_1PSIDTS
      2. A JSON file at <workspace>/gemini_cookies.json
      3. Auto-fetch from the local Edge/Chrome profile (Playwright)

    Returns a dict with keys "1psid" and "1psidts" (values may be empty).
    """
    one_psid = os.getenv("GEMINI_1PSID", "")
    one_psidts = os.getenv("GEMINI_1PSIDTS", "")

    if not one_psid:
        path = _cookie_file()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                one_psid = str(data.get("1psid", "") or data.get("__Secure-1PSID", ""))
                one_psidts = str(data.get("1psidts", "") or data.get("__Secure-1PSIDTS", ""))
            except (json.JSONDecodeError, OSError):
                one_psid = ""

    # 3. Auto-fetch from the local browser profile. This handles the
    #    App-Bound Encryption (v20) cookies that DPAPI cannot decrypt.
    #    auto_fetch_cookies() is synchronous (Playwright sync API), so it is
    #    safe to call from both sync and async contexts.
    if not one_psid:
        try:
            auto = auto_fetch_cookies()
            one_psid = auto.get("1psid", "")
            one_psidts = auto.get("1psidts", "")
        except Exception:
            one_psid = ""

    return {"1psid": one_psid.strip(), "1psidts": one_psidts.strip()}


def is_configured() -> bool:
    """True when a __Secure-1PSID cookie is available for direct calls."""
    return bool(load_cookies()["1psid"])


def _cookie_header(cookies: Dict[str, str]) -> str:
    parts = []
    if cookies.get("1psid"):
        parts.append(f"__Secure-1PSID={cookies['1psid']}")
    if cookies.get("1psidts"):
        parts.append(f"__Secure-1PSIDTS={cookies['1psidts']}")
    return "; ".join(parts)


async def _fetch_page_metadata(client: httpx.AsyncClient, headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Fetch the Gemini app HTML and extract the build label ("bl") and the
    anti-CSRF "at" token (SNlM0e). Both are required for StreamGenerate.
    """
    request_headers = {
        "User-Agent": _DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if headers:
        request_headers.update(headers)
    resp = await client.get(
        "https://gemini.google.com/app",
        headers=request_headers,
    )
    if resp.status_code != 200:
        raise GeminiDirectError(
            f"無法載入 Gemini 頁面 (HTTP {resp.status_code})。請確認 cookie 有效且未過期。"
        )

    html = resp.text
    bl_match = _BL_RE_CURRENT.search(html) or _BL_RE.search(html)
    at_match = _AT_RE.search(html)
    sid_match = _SID_RE.search(html)

    if not at_match:
        raise GeminiDirectError(
            "無法從 Gemini 頁面取得 at token (SNlM0e)。cookie 可能已失效，請重新登入並更新 cookie。"
        )

    bl = ""
    if bl_match:
        if bl_match.re is _BL_RE_CURRENT:
            bl = bl_match.group(1)
        else:
            bl = bl_match.group(0).strip('"')

    return {
        "bl": bl,
        "at": at_match.group(1),
        "f_sid": sid_match.group(1) if sid_match else "",
    }


def _build_freq(prompt: str) -> str:
    """
    Build the f.req form field for StreamGenerate. The prompt is wrapped in the
    nested JSON envelope Gemini's frontend expects.
    """
    # Keep the double-encoded envelope used by Gemini's current web client.
    # This is intentionally a small payload: conversation history is compiled
    # into `prompt` by SessionManager before this function is called.
    inner = json.dumps([[prompt], None, None], ensure_ascii=False)
    return json.dumps([None, inner], ensure_ascii=False)


_MODEL_HEADERS = {
    "gemini-web/pro": '[1,null,null,null,"9d8ca3786ebdfbea",null,null,0,[4]]',
    "gemini-web/flash": '[1,null,null,null,"9ec249fc9ad08861",null,null,0,[4]]',
    "gemini-web/flash-thinking": '[1,null,null,null,"9ec249fc9ad08861",null,null,0,[4]]',
}


def _model_headers(model: str) -> Dict[str, str]:
    value = _MODEL_HEADERS.get(model)
    return {"x-goog-ext-525001261-jspb": value} if value else {}


def _extract_stream_frames(raw: str):
    """Yield JSON roots from Gemini's XSSI/length-prefixed stream."""
    clean = re.sub(r"^\)\]\}'\s*", "", raw)
    # Some deployments return a single JSON array; handle it first.
    try:
        yield json.loads(clean)
        return
    except json.JSONDecodeError:
        pass

    pos = 0
    while pos < len(clean):
        while pos < len(clean) and clean[pos].isspace():
            pos += 1
        start = pos
        while pos < len(clean) and clean[pos].isdigit():
            pos += 1
        if start == pos or pos >= len(clean) or clean[pos] != "\n":
            break
        length = int(clean[start:pos])
        pos += 1
        frame = clean[pos:pos + length]
        if len(frame) < length:
            break
        pos += length
        try:
            yield json.loads(frame)
        except json.JSONDecodeError:
            continue


def _extract_text_from_chunk(raw: str) -> str:
    """
    Extract the assistant text from a raw StreamGenerate response fragment.

    Gemini wraps the stream in a `)]}'`-prefixed JSON array. The model text is
    buried inside nested string fields. We do a best-effort extraction:
      1. Strip the `)]}'` prefix.
      2. Walk every string in the JSON tree and keep the longest plausible
         markdown/prose candidate (reusing the same heuristics as the
         extension's network interceptor).
    """
    if not raw.strip():
        return ""

    def _collect(node, out):
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, list):
            for item in node:
                _collect(item, out)
        elif isinstance(node, dict):
            for v in node.values():
                _collect(v, out)

    strings = []
    roots = list(_extract_stream_frames(raw))
    for root in roots:
        _collect(root, strings)
    if not strings:
        strings = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)

    def _plausible(s: str) -> bool:
        if not s or len(s) < 12:
            return False
        if s.startswith(("http://", "https://", "//")):
            return False
        if re.fullmatch(r"[A-Za-z0-9_-]{12,}", s):
            return False
        if re.fullmatch(r"[A-Fa-f0-9]{12,}", s):
            return False
        return bool(re.search(r"[\s\u3000\u3400-\u9fff\u3040-\u30ff]|[.!?,:;()\[\]{}<>#*_`\-]", s))

    best = ""
    for s in strings:
        if _plausible(s) and len(s) > len(best):
            best = s
    return best


async def stream_generate(
    prompt: str,
    model: str = "gemini-web/pro",
    timeout_sec: int = 180,
) -> AsyncGenerator[TurnEvent, None]:
    """
    Send a prompt to Gemini Web directly via cookies and yield TurnEvents.

    This mirrors the TurnEvent contract used by the WebSocket hub so the rest
    of the bridge (stream_adapter, session_manager) works unchanged.
    """
    cookies = load_cookies()
    if not cookies["1psid"]:
        yield TurnEvent(
            event_type="error",
            error=(
                "未設定 Gemini cookie。請設定環境變數 GEMINI_1PSID，"
                "或建立 gemini_cookies.json ({\"1psid\": \"...\", \"1psidts\": \"...\"})。"
            ),
        )
        return

    headers = {
        "User-Agent": _DEFAULT_UA,
        "Cookie": _cookie_header(cookies),
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Origin": "https://gemini.google.com",
        "Referer": "https://gemini.google.com/app",
        "Accept": "*/*",
        "X-Same-Domain": "1",
    }

    async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
        try:
            meta = await _fetch_page_metadata(client, headers=headers)
        except GeminiDirectError as e:
            yield TurnEvent(event_type="error", error=str(e))
            return
        except httpx.HTTPError as e:
            yield TurnEvent(event_type="error", error=f"連線 Gemini 失敗: {e}")
            return

        url = STREAM_GENERATE_URL
        params = {
            "bl": meta["bl"],
            "_reqid": str(int(uuid.uuid4().int % 1_000_000)),
            "rt": "c",
        }
        if meta.get("f_sid"):
            params["f.sid"] = meta["f_sid"]
        data = {
            "f.req": _build_freq(prompt),
            "at": meta["at"],
        }

        accumulated = ""
        last_sent = ""

        try:
            async with client.stream(
                "POST", url, params=params, data=data,
                headers={**headers, **_model_headers(model)},
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", errors="replace")
                    yield TurnEvent(
                        event_type="error",
                        error=f"Gemini StreamGenerate 失敗 (HTTP {resp.status_code}): {body[:300]}",
                    )
                    return

                async for chunk in resp.aiter_text():
                    accumulated += chunk
                    text = _extract_text_from_chunk(accumulated)
                    if text and len(text) > len(last_sent):
                        delta = text[len(last_sent):]
                        last_sent = text
                        yield TurnEvent(
                            event_type="delta",
                            text=text,
                            delta=delta,
                        )

        except httpx.HTTPError as e:
            yield TurnEvent(event_type="error", error=f"Gemini 串流中斷: {e}")
            return

    if not last_sent.strip():
        yield TurnEvent(
            event_type="error",
            error="Gemini 直連未回傳任何文字。cookie 可能已失效，或帳號觸發了驗證。",
        )
        return

    yield TurnEvent(event_type="done", text=last_sent)
