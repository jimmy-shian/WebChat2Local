"""
自動抓取 Google Gemini 的 __Secure-1PSID / __Secure-1PSIDTS cookie。

重要限制（實測結論）：
  Chrome/Edge 127+ 對 Google 登入 cookie 使用 App-Bound Encryption
  (encrypted_value 前綴為 "v20")。這類 cookie 綁定到「原始瀏覽器進程的
  elevation service」，因此：

  1. DPAPI (win32crypt) 無法解密。
  2. IElevator COM 介面在非瀏覽器進程中呼叫會回 E_NOINTERFACE (0x80004002)。
  3. Playwright 啟動的「新瀏覽器進程」也讀不到這些 cookie（實測只讀得到
     NID / COMPASS 等非 ABE cookie，__Secure-1PSID 不會出現）。

  因此「全自動抓取」在 App-Bound Encryption 下沒有可靠的純本機方案。
  本模組保留 Playwright 嘗試作為 best-effort（若使用者關閉了 ABE，或
  未來 Chrome 放寬限制，即可自動生效），但**不保證成功**。

  可靠方案仍是：手動從瀏覽器 DevTools 複製 __Secure-1PSID 到
  gemini_cookies.json 或環境變數 GEMINI_1PSID。詳見 docs/DIRECT_COOKIE_SETUP.md。
"""

import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

# 需要複製的 profile 檔案（避免瀏覽器 lock 時無法讀取）。
_COPY_FILES = [
    "Local State",
    "Default/Cookies",
    "Default/Network/Cookies",
]


def _browser_candidates() -> List[Tuple[str, Path]]:
    """回傳 (playwright channel, user_data_dir) 候選，Edge 優先。"""
    home = Path.home()
    result: List[Tuple[str, Path]] = []

    edge = home / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data"
    if edge.exists():
        result.append(("msedge", edge))

    chrome = home / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
    if chrome.exists():
        result.append(("chrome", chrome))

    return result


def _list_profiles(user_data_dir: Path) -> List[str]:
    """列出 user-data-dir 下的所有 profile 目錄名稱。"""
    profiles = []
    if (user_data_dir / "Default").exists():
        profiles.append("Default")
    for d in sorted(user_data_dir.iterdir()):
        if d.is_dir() and d.name.startswith("Profile"):
            profiles.append(d.name)
    return profiles


def _copy_profile(user_data_dir: Path, profile: str, dst: Path) -> None:
    """複製指定 profile 的 cookie 檔案到暫存目錄，繞過瀏覽器 lock。"""
    dst.mkdir(parents=True, exist_ok=True)

    local_state = user_data_dir / "Local State"
    if local_state.exists():
        try:
            shutil.copy2(local_state, dst / "Local State")
        except OSError:
            pass

    src_cookies = user_data_dir / profile / "Network" / "Cookies"
    if src_cookies.exists():
        dst_cookies = dst / "Default" / "Network" / "Cookies"
        dst_cookies.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src_cookies, dst_cookies)
        except OSError:
            pass

    src_cookies_legacy = user_data_dir / profile / "Cookies"
    if src_cookies_legacy.exists():
        dst_cookies = dst / "Default" / "Cookies"
        dst_cookies.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src_cookies_legacy, dst_cookies)
        except OSError:
            pass


def _read_cookies(channel: str, user_data_dir: Path) -> Dict[str, str]:
    """用 Playwright (sync) 啟動瀏覽器並讀取 Gemini cookie。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            channel=channel,
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        try:
            cookies = context.cookies("https://gemini.google.com")
            result: Dict[str, str] = {"1psid": "", "1psidts": ""}
            for c in cookies:
                if c["name"] == "__Secure-1PSID":
                    result["1psid"] = c.get("value", "")
                elif c["name"] == "__Secure-1PSIDTS":
                    result["1psidts"] = c.get("value", "")
            return result
        finally:
            context.close()


def auto_fetch_cookies() -> Dict[str, str]:
    """
    自動抓取 __Secure-1PSID / __Secure-1PSIDTS cookie（同步，best-effort）。

    回傳 {"1psid": ..., "1psidts": ...}，抓不到時值為空字串。
    注意：App-Bound Encryption 下通常抓不到，請以手動設定為主要方案。
    """
    for channel, user_data_dir in _browser_candidates():
        profiles = _list_profiles(user_data_dir)

        try:
            cookies = _read_cookies(channel, user_data_dir)
            if cookies.get("1psid"):
                return cookies
        except Exception:
            pass

        for profile in profiles:
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    tmp_profile = Path(tmp) / "profile"
                    _copy_profile(user_data_dir, profile, tmp_profile)
                    cookies = _read_cookies(channel, tmp_profile)
                    if cookies.get("1psid"):
                        return cookies
            except Exception:
                continue

    return {"1psid": "", "1psidts": ""}