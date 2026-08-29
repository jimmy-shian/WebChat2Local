import json
import os
import subprocess
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

EXTENSION_PATH = os.path.abspath(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension")

def trace_extension_execution():
    server_proc = subprocess.Popen(
        [sys.executable, "run_server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8"
    )
    time.sleep(2)

    options = Options()
    options.add_argument(f"--load-extension={EXTENSION_PATH}")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    driver = webdriver.Chrome(options=options)
    try:
        driver.get("https://chatgpt.com")
        time.sleep(5)

        # Trigger chat completion
        import threading
        def do_req():
            try:
                payload = {
                    "model": "auto",
                    "messages": [{"role": "user", "content": "請只回覆兩個字：你好"}],
                    "stream": True
                }
                with httpx.Client(timeout=30.0) as client:
                    with client.stream("POST", "http://127.0.0.1:8765/v1/chat/completions", json=payload) as resp:
                        for line in resp.iter_lines():
                            print("  [API SSE Chunk]", line)
            except Exception as e:
                print("  [API Error]", e)

        t = threading.Thread(target=do_req)
        t.start()

        # Poll console logs every 500ms
        for i in range(20):
            time.sleep(0.5)
            logs = driver.get_log("browser")
            for log in logs:
                print(f"  [Chrome {log.get('level')}] {log.get('message')}")

        t.join(timeout=2)
    finally:
        driver.quit()
        server_proc.terminate()
        server_proc.kill()

if __name__ == "__main__":
    trace_extension_execution()
