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

def test_full_e2e_with_sync():
    print("==================================================")
    print("🚀 [FULL E2E VERIFICATION WITH WEBSOCKET SYNC]")
    print("==================================================")

    # 1. Start server
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

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get("https://chatgpt.com")
        
        # 2. Wait until WebSocket is truly connected
        print("\n[Step 1] 等待瀏覽器擴充套件連線至本地 WebSocket...")
        connected = False
        for i in range(15):
            time.sleep(1)
            try:
                h = httpx.get("http://127.0.0.1:8765/health", timeout=2.0).json()
                if h.get("browser_connected"):
                    print(f"✅ 擴充套件已連線 (耗時 {i+1}s)! Info: {h.get('client_info')}")
                    connected = True
                    break
                else:
                    print(f"  [{i+1}s] 等待連線中...")
            except Exception:
                pass

        if not connected:
            print("❌ 擴充套件連線逾時！")
            return

        # 3. Send Chat Completion
        print("\n[Step 2] 發送測試 Prompt 到 /v1/chat/completions ...")
        payload = {
            "model": "auto",
            "messages": [{"role": "user", "content": "請只回覆兩個字：你好"}],
            "stream": True
        }

        import threading
        chunks = []
        def make_req():
            try:
                with httpx.Client(timeout=40.0) as client:
                    with client.stream("POST", "http://127.0.0.1:8765/v1/chat/completions", json=payload) as resp:
                        print(f"API 回應狀態碼: {resp.status_code}")
                        for line in resp.iter_lines():
                            if line:
                                print("📡 [收到 SSE 流]", line)
                                chunks.append(line)
            except Exception as e:
                print("HTTP 請求異常:", e)

        t = threading.Thread(target=make_req)
        t.start()

        # 4. Monitor browser Console & DOM
        for i in range(15):
            time.sleep(1)
            poll = driver.execute_script("""
                const assistants = Array.from(document.querySelectorAll('[data-message-author-role="assistant"], article, div.markdown, div.prose, div[class*="agent-turn"]'));
                const texts = assistants.map(a => (a.innerText || '').trim()).filter(t => t.length > 0);
                const stopBtn = document.querySelector('button[data-testid="stop-button"], button[aria-label*="Stop"]');
                return {
                    texts: texts.slice(-2),
                    stop_btn: !!stopBtn
                };
            """)
            print(f"[{i+1}s] StopBtn: {poll['stop_btn']}, 網頁擷取文字: {poll['texts']}")
            
            for l in driver.get_log("browser"):
                if "WebChat2Local" in l.get("message", ""):
                    print(f"  [Chrome Console] {l.get('message')}")

            if len(chunks) > 2 and "[DONE]" in str(chunks[-1]):
                print("🎉🎉🎉 成功收到 [DONE]！串流傳輸完全成功！")
                break

        t.join(timeout=5)
        print(f"\n測試結束，總共收到 {len(chunks)} 個 SSE 數據包！")

    finally:
        if driver:
            time.sleep(2)
            driver.quit()
        if server_proc:
            server_proc.terminate()
            server_proc.kill()

if __name__ == "__main__":
    test_full_e2e_with_sync()
