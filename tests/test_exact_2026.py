import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def test_exact_2026_selectors():
    options = Options()
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get("https://chatgpt.com")
        time.sleep(6)
        
        # Exact typing & submission script for 2026 ChatGPT
        send_res = driver.execute_script("""
            const textarea = document.querySelector('textarea.wm-composer-textarea, #mobile-composer-prompt, #prompt-textarea, textarea, [contenteditable="true"]');
            if (!textarea) return { error: 'No textarea' };
            
            textarea.focus();
            textarea.value = '請只回覆兩個字：你好';
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
            textarea.dispatchEvent(new Event('change', { bubbles: true }));
            
            // Exact submit button selector
            const submitBtn = document.querySelector('button.wm-composer-submitButton, button[type="submit"], button[data-testid="send-button"], button[aria-label*="傳送"], button[aria-label*="Send"]');
            
            let submitted = false;
            if (submitBtn && !submitBtn.disabled) {
                submitBtn.click();
                submitted = true;
            } else {
                const form = document.querySelector('form');
                if (form) {
                    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
                    submitted = true;
                }
            }
            
            return {
                textarea_id: textarea.id,
                submit_btn_class: submitBtn ? submitBtn.className : null,
                submitted: submitted
            };
        """)
        print("Submit Result:\n", json.dumps(send_res, indent=2, ensure_ascii=False))
        
        print("\nObserving ChatGPT response for 12 seconds...")
        for i in range(12):
            time.sleep(1)
            poll = driver.execute_script("""
                const textNodes = Array.from(document.querySelectorAll('div, p, span, article')).map(el => el.innerText || '').filter(t => t.includes('你好'));
                const last = textNodes.length > 0 ? textNodes[textNodes.length - 1] : '';
                return {
                    found: textNodes.length > 0,
                    text: last.slice(0, 100)
                };
            """)
            print(f"[{i+1}s] Found response: {poll['found']}, Content: '{poll['text']}'")
            if poll['found'] and i > 2:
                print("\n🎉 SUCCESS! ChatGPT responded and text was captured live in Anonymous mode!")
                break
                
    finally:
        driver.quit()

if __name__ == "__main__":
    test_exact_2026_selectors()
