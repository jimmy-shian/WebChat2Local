import json
import os
import subprocess
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

EXTENSION_PATH = os.path.abspath(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension")

def run_test():
    print("==================================================")
    print("[TEST] Launching Selenium + Chrome for ChatGPT Web")
    print("==================================================")

    # 1. Start WebChat2Local server
    print("[1/4] Starting local server...")
    server_proc = subprocess.Popen(
        [sys.executable, "run_server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8"
    )
    time.sleep(2)

    # 2. Launch Chrome with Extension
    print(f"[2/4] Launching Chrome with extension: {EXTENSION_PATH} ...")
    options = Options()
    options.add_argument(f"--load-extension={EXTENSION_PATH}")
    options.add_argument("--disable-gpu")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        print("Chrome started. Navigating to https://chatgpt.com ...")
        driver.get("https://chatgpt.com")
        time.sleep(6)

        print("Page Title:", driver.title)
        print("Current URL:", driver.current_url)

        # 3. Check browser console logs
        print("\n--- Browser Console Logs (Initial) ---")
        try:
            logs = driver.get_log("browser")
            for log in logs:
                print(f"[{log.get('level')}] {log.get('message')}")
        except Exception as e:
            print("Log reading error:", e)

        # 4. Check if WebSocket connected
        print("\n[3/4] Checking /health endpoint...")
        try:
            health = httpx.get("http://127.0.0.1:8765/health", timeout=5.0).json()
            print("Health Status:", json.dumps(health, indent=2, ensure_ascii=False))
        except Exception as e:
            print("Health check failed:", e)

        # 5. Send a Chat Completion Request
        print("\n[4/4] Sending test prompt to http://127.0.0.1:8765/v1/chat/completions ...")
        payload = {
            "model": "auto",
            "messages": [{"role": "user", "content": "請只回覆兩個字：你好"}],
            "stream": True
        }

        with httpx.Client(timeout=40.0) as client:
            with client.stream("POST", "http://127.0.0.1:8765/v1/chat/completions", json=payload) as response:
                print(f"API Response HTTP Status: {response.status_code}")
                for line in response.iter_lines():
                    if line:
                        print("SSE Received:", line)

        # Re-check browser console logs
        print("\n--- Browser Console Logs (After Request) ---")
        try:
            logs = driver.get_log("browser")
            for log in logs:
                print(f"[{log.get('level')}] {log.get('message')}")
        except Exception as e:
            print("Log reading error:", e)

    except Exception as e:
        print("\n[ERROR] Test exception:", e)
    finally:
        if driver:
            print("\nWaiting 5 seconds before closing browser...")
            time.sleep(5)
            driver.quit()
        if server_proc:
            server_proc.terminate()
            server_proc.kill()
        print("\nTest finished.")

if __name__ == "__main__":
    run_test()
