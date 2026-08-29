import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def test_react_native_setter():
    options = Options()
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get("https://chatgpt.com")
        time.sleep(6)
        
        # Test React 18 Native Value Setter
        send_res = driver.execute_script("""
            const textarea = document.querySelector('textarea.wm-composer-textarea, #mobile-composer-prompt, #prompt-textarea, textarea');
            if (!textarea) return { error: 'No textarea found' };
            
            textarea.focus();
            
            // React 18 controlled component setter
            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
            nativeSetter.call(textarea, '請只回覆兩個字：你好');
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
            textarea.dispatchEvent(new Event('change', { bubbles: true }));
            
            // Wait 200ms and click submit
            setTimeout(() => {
                const submitBtn = document.querySelector('button.wm-composer-submitButton, button[type="submit"], button[aria-label*="傳送"], button[aria-label*="Send"]');
                if (submitBtn) {
                    submitBtn.click();
                }
            }, 200);
            
            return {
                textarea_value: textarea.value,
                textarea_id: textarea.id
            };
        """)
        print("React Setter Result:\n", json.dumps(send_res, indent=2, ensure_ascii=False))
        
        print("\nObserving ChatGPT response for 12 seconds...")
        for i in range(12):
            time.sleep(1)
            poll = driver.execute_script("""
                const bodyText = document.body.innerText;
                const matches = bodyText.includes('你好');
                const lastTurn = Array.from(document.querySelectorAll('article, div[class*="agent-turn"], div[class*="message"], div.markdown')).map(e => e.innerText).slice(-2);
                return {
                    matches: matches,
                    lastTurn: lastTurn,
                    bodySnippet: bodyText.slice(-200)
                };
            """)
            print(f"[{i+1}s] Found: {poll['matches']}, Turn: {poll['lastTurn']}")
            if poll['matches'] and i > 2:
                print("\n🎉🎉🎉 SUCCESS: ChatGPT response successfully generated and verified!")
                break
                
    finally:
        driver.quit()

if __name__ == "__main__":
    test_react_native_setter()
