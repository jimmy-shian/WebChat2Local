import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def inspect_chatgpt_network_requests():
    print("==================================================")
    print("🚀 [RECORD CHATGPT REAL API REQUEST PAYLOAD]")
    print("==================================================")

    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    
    driver = webdriver.Chrome(options=options)
    try:
        driver.get("https://chatgpt.com")
        time.sleep(6)

        # Type and submit to capture the real conversation network request
        driver.execute_script("""
            const textarea = document.querySelector('textarea, #mobile-composer-prompt, #prompt-textarea');
            if (textarea) {
                textarea.focus();
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
                if (nativeSetter) nativeSetter.call(textarea, 'Hi');
                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                setTimeout(() => {
                    const btn = document.querySelector('button.wm-composer-submitButton, button[type="submit"]');
                    if (btn) btn.click();
                }, 300);
            }
        """)

        time.sleep(5)

        # Parse performance logs for network requests
        logs = driver.get_log("performance")
        captured_requests = []
        for entry in logs:
            try:
                log_obj = json.loads(entry["message"])
                msg = log_obj.get("message", {})
                method = msg.get("method")
                if method == "Network.requestWillBeSent":
                    req = msg.get("params", {}).get("request", {})
                    url = req.get("url", "")
                    if "conversation" in url or "sentinel" in url or "backend" in url:
                        captured_requests.append({
                            "url": url,
                            "method": req.get("method"),
                            "headers": req.get("headers"),
                            "postData": req.get("postData")
                        })
            except Exception:
                pass

        print(f"Captured {len(captured_requests)} relevant API requests:")
        for r in captured_requests:
            print(f"\n--- {r['method']} {r['url']} ---")
            print("Headers:", json.dumps({k: v for k, v in r['headers'].items() if k.lower() in ['authorization', 'content-type', 'oai-device-id']}, indent=2))
            if r.get('postData'):
                try:
                    parsed = json.loads(r['postData'])
                    print("Body:", json.dumps(parsed, indent=2, ensure_ascii=False)[:300])
                except Exception:
                    print("Body:", r['postData'][:200])

    finally:
        driver.quit()

if __name__ == "__main__":
    inspect_chatgpt_network_requests()
