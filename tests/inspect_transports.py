import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def inspect_all_transport_protocols():
    print("==================================================")
    print("🚀 [INSPECT ALL TRANSPORT PROTOCOLS ON CHATGPT & GEMINI]")
    print("==================================================")

    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"})
    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://chatgpt.com")
        time.sleep(6)

        # Hook WebSocket, EventSource, Fetch, XHR
        driver.execute_script("""
            window.__traffic_log = [];

            // 1. WebSocket Hook
            const origWS = window.WebSocket;
            window.WebSocket = function(...args) {
                const ws = new origWS(...args);
                window.__traffic_log.push({ type: 'WS_OPEN', url: args[0] });
                ws.addEventListener('message', (e) => {
                    window.__traffic_log.push({ type: 'WS_MSG', data: typeof e.data === 'string' ? e.data.slice(0, 200) : 'binary' });
                });
                return ws;
            };

            // 2. EventSource Hook
            const origES = window.EventSource;
            window.EventSource = function(...args) {
                const es = new origES(...args);
                window.__traffic_log.push({ type: 'ES_OPEN', url: args[0] });
                es.onmessage = (e) => {
                    window.__traffic_log.push({ type: 'ES_MSG', data: e.data ? e.data.slice(0, 200) : '' });
                };
                return es;
            };
        """)

        # Submit prompt
        driver.execute_script("""
            const textarea = document.querySelector('textarea, #mobile-composer-prompt, #prompt-textarea');
            if (textarea) {
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
                if (nativeSetter) nativeSetter.call(textarea, '請只回覆兩個字：你好');
                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                setTimeout(() => {
                    const btn = document.querySelector('button.wm-composer-submitButton, button[type="submit"]');
                    if (btn) btn.click();
                }, 300);
            }
        """)

        time.sleep(6)

        traffic = driver.execute_script("return window.__traffic_log || [];")
        print(f"Captured {len(traffic)} WS/ES events:")
        for t in traffic[:20]:
            print(" ", t)

    finally:
        driver.quit()

if __name__ == "__main__":
    inspect_all_transport_protocols()
