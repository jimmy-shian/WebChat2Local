import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def inspect_live_gemini_output():
    print("==================================================")
    print("🚀 [INSPECT LIVE GEMINI OUTPUT STRUCTURE]")
    print("==================================================")

    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://gemini.google.com/app?hl=zh-TW")
        time.sleep(6)

        # Type a prompt requesting XML and formatting
        driver.execute_script("""
            const editor = document.querySelector('div.ql-editor[contenteditable="true"], rich-textarea div[contenteditable="true"]');
            if (editor) {
                editor.focus();
                document.execCommand('selectAll', false, null);
                document.execCommand('insertText', false, '請用 <attempt_completion><result>測試結果</result></attempt_completion> 回覆我');
                editor.dispatchEvent(new Event('input', { bubbles: true }));
                setTimeout(() => {
                    const btn = document.querySelector('button.send-button, button[aria-label*="傳送"], button[aria-label*="Send"]');
                    if (btn) btn.click();
                }, 300);
            }
        """)

        print("Waiting for Gemini response...")
        time.sleep(10)

        # Inspect DOM structure of Gemini response container
        res_info = driver.execute_script("""
            const containers = Array.from(document.querySelectorAll('model-response, message-content, div.model-response-text, [id^="message-content-id-"]'));
            
            return containers.map(c => ({
                tagName: c.tagName,
                className: c.className,
                id: c.id,
                innerHTML_sample: c.innerHTML.slice(0, 500),
                innerText_sample: c.innerText.slice(0, 500),
                children_tags: Array.from(c.children).map(ch => ch.tagName)
            }));
        """)

        print("Gemini Response Containers:\n", json.dumps(res_info, indent=2, ensure_ascii=False))

    finally:
        driver.quit()

if __name__ == "__main__":
    inspect_live_gemini_output()
