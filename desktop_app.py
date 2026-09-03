"""
Desktop background application for Gemini Web to Local Bridge.
Features:
  - System Tray icon (pystray) with 0 disk wear.
  - Runs FastAPI Uvicorn server in a daemon thread.
  - One-click tray menu actions (Dashboard, Antigravity setup, clipboard copy).
"""

import sys
import os
import threading
import time
import webbrowser
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn
from PIL import Image, ImageDraw
import pystray

from server.config import SERVER_HOST, SERVER_PORT, BASE_URL
from server.antigravity.installer import install_antigravity_integration


def create_tray_icon_image():
    """Generates an in-memory 64x64 blue Gemini 'G' icon with 0 disk write."""
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Outer circle
    draw.ellipse((4, 4, 60, 60), fill="#2563eb", outline="#60a5fa", width=2)
    # Inner decorative arc
    draw.arc((12, 12, 52, 52), start=45, end=315, fill="#ffffff", width=4)
    # Center dot
    draw.ellipse((28, 28, 36, 36), fill="#ffffff")
    return image


def start_uvicorn():
    """Starts Uvicorn server in daemon thread."""
    from server.bridge.ws_hub import setup_clean_logging
    setup_clean_logging()

    config = uvicorn.Config(
        "server.app:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level="info",
        access_log=True,
        log_config=None,
    )
    server = uvicorn.Server(config)
    server.run()


def open_dashboard(icon, item):
    webbrowser.open(f"http://{SERVER_HOST}:{SERVER_PORT}")


def run_antigravity_setup(icon, item):
    res = install_antigravity_integration()
    icon.notify("Google Antigravity MCP 設定已成功更新！", title="Gemini Web Bridge")


def copy_api_endpoint(icon, item):
    try:
        import pyperclip
        pyperclip.copy(f"{BASE_URL}/v1")
        icon.notify(f"API 端點已複製: {BASE_URL}/v1", title="Gemini Web Bridge")
    except Exception:
        pass


def exit_action(icon, item):
    icon.stop()
    os._exit(0)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    print("[WebChat2Local] ==================================================")
    print(f"[WebChat2Local] Gemini Web Bridge -> {BASE_URL}")
    print(f"[WebChat2Local] Python executable: {sys.executable}")
    print("[WebChat2Local] Browser extension events and turn traffic will be logged below.")
    print("[WebChat2Local] ==================================================")
    
    # 1. Start Uvicorn in background thread
    server_thread = threading.Thread(target=start_uvicorn, daemon=True)
    server_thread.start()
    
    # 2. Wait briefly and open browser
    time.sleep(1.2)
    webbrowser.open(f"http://{SERVER_HOST}:{SERVER_PORT}")
    
    # 3. Create Tray menu
    menu = pystray.Menu(
        pystray.MenuItem("開啟儀表板 (Dashboard)", open_dashboard, default=True),
        pystray.MenuItem("Antigravity 一鍵設定", run_antigravity_setup),
        pystray.MenuItem("複製 API 端點 (Base URL)", copy_api_endpoint),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("結束 (Exit)", exit_action),
    )
    
    icon_image = create_tray_icon_image()
    icon = pystray.Icon(
        "GeminiWeb2Local",
        icon_image,
        "Gemini Web to Local Bridge",
        menu
    )
    
    # 4. Run tray icon in main thread
    icon.run()


if __name__ == "__main__":
    main()
