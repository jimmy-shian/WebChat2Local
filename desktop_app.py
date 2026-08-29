"""
WebChat2Local Desktop Application
One-click portable background server with system tray icon for Windows and macOS.

Hardware Protection Principles:
- SSD: 0 disk log writes, purely in-memory buffer, zero temp-file churn.
- RAM: Bounded queue, instant GC on disconnect, low idle footprint (~25MB).
"""

import argparse
import ctypes
import os
import sys
import threading
import time
import webbrowser
from typing import Optional

import io

# Ensure stdout and stderr are always valid streams (even under PyInstaller --noconsole / GUI mode)
if sys.stdout is None:
    sys.stdout = io.StringIO()
elif hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if sys.stderr is None:
    sys.stderr = io.StringIO()
elif hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

if sys.platform == "win32":
    try:
        os.system("")
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        if handle and handle != -1:
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass

import uvicorn
from PIL import Image, ImageDraw

# Server instance
from server.server import app

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765
DASHBOARD_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
API_BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}/v1"

server_thread: Optional[threading.Thread] = None
uvicorn_server: Optional[uvicorn.Server] = None
tray_icon = None
shutdown_event = threading.Event()


def create_tray_icon_image(size: int = 64) -> Image.Image:
    """
    Generates a crisp, developer-grade geometric icon in memory.
    Zero SSD read/write overhead.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark rounded background
    pad = 4
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=14,
        fill=(15, 23, 42, 255),       # Slate-900
        outline=(59, 130, 246, 255),   # Blue-500
        width=3,
    )

    # Bright emerald glowing central node (represents active gateway)
    center = size // 2
    r_outer = 12
    draw.ellipse(
        [center - r_outer, center - r_outer, center + r_outer, center + r_outer],
        fill=(16, 185, 129, 255),     # Emerald-500
    )

    r_inner = 6
    draw.ellipse(
        [center - r_inner, center - r_inner, center + r_inner, center + r_inner],
        fill=(255, 255, 255, 255),   # White core
    )

    return img


def run_uvicorn_server(host: str, port: int):
    """Runs Uvicorn server in a controlled thread."""
    global uvicorn_server
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="warning",  # Minimize console noise & eliminate disk I/O
        access_log=False,
    )
    uvicorn_server = uvicorn.Server(config)
    try:
        uvicorn_server.run()
    except Exception as e:
        print(f"[WebChat2Local] Server error: {e}")


def open_url(url: str):
    """Opens a URL in default web browser."""
    threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()


def copy_to_clipboard(text: str):
    """Copies text to clipboard across platforms."""
    try:
        if sys.platform == "win32":
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
        elif sys.platform == "darwin":
            import subprocess
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, close_fds=True)
            p.communicate(input=text.encode("utf-8"))
    except Exception:
        pass


def on_open_dashboard(icon, item):
    open_url(DASHBOARD_URL)


def on_open_deepseek(icon, item):
    open_url("https://chat.deepseek.com")


def on_open_chatgpt(icon, item):
    open_url("https://chatgpt.com")


def on_open_gemini(icon, item):
    open_url("https://gemini.google.com")


def on_copy_api_url(icon, item):
    copy_to_clipboard(API_BASE_URL)
    if icon and hasattr(icon, "notify"):
        try:
            icon.notify(f"已複製: {API_BASE_URL}", "WebChat2Local")
        except Exception:
            pass


def on_exit(icon, item):
    """Graceful shutdown of server and tray icon."""
    print("\n[WebChat2Local] 正在關閉伺服器並退出...")
    shutdown_event.set()
    if uvicorn_server:
        uvicorn_server.should_exit = True
    if icon:
        icon.stop()


def setup_tray(host: str, port: int, auto_open: bool = True):
    """Sets up and starts the system tray icon."""
    global tray_icon

    try:
        import pystray
    except ImportError:
        print("[WebChat2Local] pystray 未安裝，將以無圖示背景模式運行。")
        run_headless(host, port)
        return

    icon_img = create_tray_icon_image()

    menu = pystray.Menu(
        pystray.MenuItem("🌐 開啟控制面板 (Dashboard)", on_open_dashboard, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🔮 開啟 DeepSeek 網頁", on_open_deepseek),
        pystray.MenuItem("🤖 開啟 ChatGPT 網頁", on_open_chatgpt),
        pystray.MenuItem("♊ 開啟 Gemini 網頁", on_open_gemini),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"📋 複製 Base URL ({API_BASE_URL})", on_copy_api_url),
        pystray.MenuItem(f"🟢 伺服器狀態: 運行中 (Port {port})", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌ 結束退出 (Exit)", on_exit),
    )

    tray_icon = pystray.Icon(
        name="WebChat2Local",
        icon=icon_img,
        title=f"WebChat2Local Gateway (:{port})",
        menu=menu,
    )

    # Start server in background daemon thread
    server_th = threading.Thread(
        target=run_uvicorn_server,
        args=(host, port),
        daemon=True,
        name="WebChat2LocalServer",
    )
    server_th.start()

    print("=================================================================")
    print("🚀 WebChat2Local Gateway 已在背景啟動！")
    print("=================================================================")
    print(f"📡 本地 API 網址:  {API_BASE_URL}")
    print(f"📊 控制儀表板:     {DASHBOARD_URL}")
    print(f"🤖 支援網頁平台:   DeepSeek / ChatGPT / Google Gemini")
    print("💡 程式已常駐於系統匣 (System Tray)，點擊右下角圖示可隨時管理。")
    print("=================================================================")

    # Auto-open dashboard in browser
    if auto_open:
        threading.Timer(1.0, lambda: open_url(DASHBOARD_URL)).start()

    # Run tray event loop (blocks main thread cleanly)
    tray_icon.run()


def run_headless(host: str, port: int, auto_open: bool = False):
    """Runs without GUI/Tray."""
    print("=================================================================")
    print("🚀 WebChat2Local Gateway (Headless Mode)")
    print(f"📡 本地 API:  http://{host}:{port}/v1")
    print(f"📊 控制面板:  http://{host}:{port}")
    print("=================================================================")
    if auto_open:
        threading.Timer(1.0, lambda: open_url(f"http://{host}:{port}")).start()
    run_uvicorn_server(host, port)


def main():
    parser = argparse.ArgumentParser(description="WebChat2Local Desktop App & Gateway")
    parser.add_argument("--host", default=SERVER_HOST, help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=SERVER_PORT, help="Server port (default: 8765)")
    parser.add_argument("--no-gui", action="store_true", help="Run without system tray icon (console mode)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open dashboard in browser")

    args = parser.parse_args()

    if args.no_gui:
        run_headless(args.host, args.port, auto_open=not args.no_browser)
    else:
        setup_tray(args.host, args.port, auto_open=not args.no_browser)


if __name__ == "__main__":
    main()
