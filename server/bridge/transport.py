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
    return {
        "mode": get_mode(),
        "valid_modes": list(VALID_MODES),
        "direct_configured": direct_is_configured(),
        "browser_connected": hub.is_connected,
    }


class TransportUnavailable(Exception):
    """Raised when the selected transport cannot serve a turn."""


def _direct_ok() -> bool:
    return bool(DIRECT_FALLBACK_ENABLED and direct_is_configured())


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
            return hub.execute_turn(prompt=prompt, model=model, is_new_session=is_new_session), "extension"
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

    # auto mode: Direct-first when cookies configured, extension fallback
    if _direct_ok():
        return direct_stream_generate(
            prompt=prompt,
            model=model,
            session_id=session_id,
            is_continuation=is_continuation,
            files=files,
        ), "direct"
    if hub.is_connected:
        return hub.execute_turn(prompt=prompt, model=model, is_new_session=is_new_session), "extension"

    raise TransportUnavailable(
        "Gemini Web 瀏覽器擴充套件未連線，且沒有可用的 cookie 直連設定。"
        "開啟 https://gemini.google.com 讓擴充套件自動同步 cookie，"
        "或設定 GEMINI_1PSID / gemini_cookies.json。"
    )