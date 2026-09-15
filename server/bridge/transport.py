"""
Unified transport dispatcher for Gemini turns.

Single source of truth for choosing between the two available transports:

  - "direct"    : cookie-authenticated HTTP straight to gemini.google.com
                  (no browser tab required; uses __Secure-1PSID cookies)
  - "extension" : browser extension WebSocket hub (requires a Gemini tab)

Modes (runtime-selectable from the dashboard via /v1/transport):
  - "auto"      : direct-first when cookies are configured, extension fallback
  - "direct"    : force the cookie path
  - "extension" : force the browser extension path

Every endpoint (chat completions, responses API, dashboard test turn) goes
through resolve_turn() so the selection logic is never duplicated.
"""

import os
import threading
from typing import AsyncGenerator, Tuple, Optional, List, Any

from server.config import DIRECT_FALLBACK_ENABLED, DIRECT_ONLY
from server.browser.gemini_direct import (
    is_configured as direct_is_configured,
    stream_generate as direct_stream_generate,
)
from server.browser.deepseek_direct import (
    is_configured as deepseek_is_configured,
    stream_generate as deepseek_stream_generate,
)
from server.bridge.ws_hub import hub

VALID_MODES = ("auto", "direct", "extension")

_mode_lock = threading.Lock()


def _default_mode() -> str:
    mode = os.getenv("W2L_TRANSPORT", "direct").strip().lower()
    return mode if mode in VALID_MODES else "direct"


_mode: str = _default_mode()


def get_mode() -> str:
    """Current transport selection mode ('auto' | 'direct' | 'extension')."""
    with _mode_lock:
        return _mode


def set_mode(mode: str) -> str:
    """Set the transport selection mode. Returns the normalized value."""
    normalized = str(mode or "").strip().lower()
    if normalized not in VALID_MODES:
        raise ValueError(
            f"Invalid transport mode '{mode}'. Valid modes: {', '.join(VALID_MODES)}."
        )
    with _mode_lock:
        global _mode
        _mode = normalized
    return normalized


def transport_snapshot() -> dict:
    """Status snapshot for /v1/status and the dashboard."""
    try:
        platforms = hub.connected_platforms()
    except Exception:
        platforms = {}
    return {
        "mode": get_mode(),
        "valid_modes": list(VALID_MODES),
        "direct_configured": direct_is_configured(),
        "deepseek_configured": deepseek_is_configured(),
        "browser_connected": hub.is_connected,
        "platforms": platforms,
        "active_tabs": len(hub.active_connections),
    }


# Generic route id: no platform implied by the name, so the dispatcher must
# look at the actually connected tabs instead of guessing from the model.
GENERIC_MODELS = ("webchat/auto", "webchat", "auto")


def _connected_platforms() -> set:
    """Set of normalized platforms with at least one connected tab."""
    try:
        return set(hub.connected_platforms().keys())
    except Exception:
        return set()


class TransportUnavailable(Exception):
    """Raised when the selected transport cannot serve a turn."""


def _direct_ok() -> bool:
    return bool(DIRECT_FALLBACK_ENABLED and direct_is_configured())


def _deepseek_ok() -> bool:
    try:
        return bool(deepseek_is_configured())
    except Exception:
        return False


def _is_deepseek_model(model: Optional[str]) -> bool:
    return "deepseek" in (model or "").lower()


def resolve_turn(
    prompt: str,
    model: str,
    is_new_session: bool = True,
    session_id: Optional[str] = None,
    is_continuation: bool = False,
    files: Optional[list] = None,
) -> Tuple[AsyncGenerator, str]:
    """
    Resolve a prompt into (turn_generator, transport_name) using the current
    mode. Passes session_id, is_continuation, and files to stateful direct engine.
    """
    mode = get_mode()
    is_chatgpt_req = "chatgpt" in (model or "").lower()
    is_deepseek_req = _is_deepseek_model(model)
    is_generic = (model or "").strip().lower() in GENERIC_MODELS

    # ChatGPT 模型只能透過瀏覽器擴充套件（chatgpt.com 分頁）服務。
    # 無論傳輸模式為何，都不允許落入 Gemini 直連，否則模型選擇會被忽略。
    # 注意：用「各分頁平台普查」而非 browser_info（後者只是最後回報者，
    # 雙開分頁時會翻轉，曾造成明明有 ChatGPT 分頁卻誤判）。
    if is_chatgpt_req:
        plats = _connected_platforms()
        if hub.is_connected and ("chatgpt" in plats or "unknown" in plats):
            return hub.execute_turn(prompt=prompt, model=model, is_new_session=is_new_session, platform="chatgpt"), "extension"
        if hub.is_connected:
            raise TransportUnavailable(
                "已指定 ChatGPT 模型，但目前連線的分頁只有 Gemini。"
                "請開啟 https://chatgpt.com 分頁後重試。"
            )
        raise TransportUnavailable(
            "已指定 ChatGPT 模型，但瀏覽器擴充套件尚未連線。"
            "請在 Chrome 或 Edge 開啟 https://chatgpt.com/ 頁面。"
        )

    # DeepSeek 模型一律走 userToken + PoW 直連（無擴充套件路徑）。
    # 不受 Gemini Cookie / transport mode 限制，mode 僅影響 Gemini/通用模型。
    if is_deepseek_req:
        if not _deepseek_ok():
            raise TransportUnavailable(
                "已指定 DeepSeek 模型，但尚未設定 DeepSeek Token。"
                "請登入 https://chat.deepseek.com/a/chat/，在 DevTools Console 執行 "
                "copy(JSON.parse(localStorage.getItem(\"userToken\")).value)，"
                "存入 deepseek_token.json {\"token\": \"...\"} 或環境變數 DEEPSEEK_TOKEN。"
            )
        return deepseek_stream_generate(
            prompt=prompt,
            model=model,
            session_id=session_id,
            is_continuation=is_continuation,
            files=files,
        ), "deepseek-direct"

    if mode == "direct":
        if not DIRECT_FALLBACK_ENABLED:
            raise TransportUnavailable(
                "直連模式已選擇，但直連功能已停用 (W2L_DIRECT_FALLBACK=0)。"
            )
        if not direct_is_configured():
            raise TransportUnavailable(
                "直連模式已選擇，但尚未設定 Gemini cookie。"
                "請開啟 gemini.google.com 讓擴充套件自動同步，"
                "或手動設定 GEMINI_1PSID / gemini_cookies.json。"
            )
        return direct_stream_generate(
            prompt=prompt,
            model=model,
            session_id=session_id,
            is_continuation=is_continuation,
            files=files,
        ), "direct"

    if mode == "extension":
        if hub.is_connected:
            # 通用模型：若只連了一種平台，直接指定，避免按模型名誤判分頁。
            plats = _connected_platforms() - {"unknown"}
            single = next(iter(plats)) if len(plats) == 1 else None
            return hub.execute_turn(prompt=prompt, model=model, is_new_session=is_new_session, platform=single), "extension"
        if _direct_ok():
            # Graceful fallback to direct cookie when extension is chosen but not currently open
            return direct_stream_generate(
                prompt=prompt,
                model=model,
                session_id=session_id,
                is_continuation=is_continuation,
                files=files,
            ), "direct"
        raise TransportUnavailable(
            "Web 視窗模式已選擇，但瀏覽器擴充套件尚未連線。"
            "請開啟 https://gemini.google.com 頁面。"
        )

    # auto mode: Direct-first when cookies configured, extension fallback.
    # 例外：通用模型 (webchat/auto) 且「只」連了 ChatGPT 分頁時，強制走擴充套件。
    # 否則只要 cookie 還在，auto 永遠走 Gemini 直連，開了 ChatGPT 分頁也沒用。
    if is_generic and hub.is_connected:
        plats = _connected_platforms() - {"unknown"}
        if plats == {"chatgpt"}:
            return hub.execute_turn(prompt=prompt, model=model, is_new_session=is_new_session, platform="chatgpt"), "extension"
    if _direct_ok():
        return direct_stream_generate(
            prompt=prompt,
            model=model,
            session_id=session_id,
            is_continuation=is_continuation,
            files=files,
        ), "direct"
    # 通用模型在無 Gemini Cookie 但有 DeepSeek Token 時改走 DeepSeek 直連。
    if is_generic and _deepseek_ok():
        return deepseek_stream_generate(
            prompt=prompt,
            model="deepseek-web/auto",
            session_id=session_id,
            is_continuation=is_continuation,
            files=files,
        ), "deepseek-direct"
    if hub.is_connected:
        plats = _connected_platforms() - {"unknown"}
        single = next(iter(plats)) if is_generic and len(plats) == 1 else None
        return hub.execute_turn(prompt=prompt, model=model, is_new_session=is_new_session, platform=single), "extension"

    raise TransportUnavailable(
        "瀏覽器擴充套件未連線 (請開啟 https://chatgpt.com 或 https://gemini.google.com)，"
        "且沒有可用的 Gemini cookie / DeepSeek Token 直連設定。"
    )
