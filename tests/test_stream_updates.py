import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def test_intercept_conversation_updates():
    print("==================================================")
    print("🚀 [TEST INTERCEPTING /unauth-mweb/conversation/updates]")
    print("==================================================")

    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://chatgpt.com")
        time.sleep(6)

        # Inject unified fetch & XHR interceptor
        driver.execute_script("""
            window.__intercepted_chunks = [];
            const originalFetch = window.fetch;
            
            window.fetch = async function(...args) {
                const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
                const response = await originalFetch.apply(this, args);
                
                if (url.includes('conversation/updates') || url.includes('StreamGenerate') || url.includes('backend')) {
                    console.log('[DEBUG INTERCEPTOR] Matched stream URL:', url);
                    const clone = response.clone();
                    const reader = clone.body.getReader();
                    const decoder = new TextDecoder('utf-8');
                    
                    (async () => {
                        try {
                            while(true) {
                                const { value, done } = await reader.read();
                                if (done) {
                                    console.log('[DEBUG INTERCEPTOR] Stream finished.');
                                    break;
                                }
                                const chunk = decoder.decode(value, { stream: true });
                                window.__intercepted_chunks.push(chunk);
                                console.log('[DEBUG INTERCEPTOR] Raw chunk received, len:', chunk.length);
                            }
                        } catch(e) {
                            console.error('[DEBUG INTERCEPTOR] Reader error:', e);
                        }
                    })();
                }
                return response;
            };
            console.log('[DEBUG INTERCEPTOR] Hooked window.fetch.');
        """)

        # Trigger prompt input and submit
        driver.execute_script("""
            const textarea = document.querySelector('textarea.wm-composer-textarea, #mobile-composer-prompt, textarea');
            if (textarea) {
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
                nativeSetter.call(textarea, '請只回覆兩個字：你好');
                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                setTimeout(() => {
                    const btn = document.querySelector('button.wm-composer-submitButton, button[type="submit"]');
                    if (btn) btn.click();
                }, 300);
            }
        """)

        print("\nMonitoring intercepted network chunks for 10 seconds...")
        for i in range(10):
            time.sleep(1)
            chunks = driver.execute_script("return window.__intercepted_chunks || [];")
            print(f"[{i+1}s] Intercepted Chunks Count: {len(chunks)}")
            if len(chunks) > 0:
                print("First chunk sample (first 300 chars):\n", chunks[0][:300])
                print("\nTotal text length across all chunks:", sum(len(c) for c in chunks))
                print("\n🎉🎉🎉 RAW NETWORK STREAM INTERCEPTION 100% SUCCESSFUL!")
                break

    finally:
        driver.quit()

if __name__ == "__main__":
    test_intercept_conversation_updates()
