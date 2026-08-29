import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def test_gemini_interaction():
    print("==================================================")
    print("🚀 [TEST GEMINI WEB TYPING & SENDING]")
    print("==================================================")

    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://gemini.google.com/app?hl=zh-TW")
        time.sleep(6)

        # 1. Type into Gemini Quill Editor
        send_res = driver.execute_script("""
            const editor = document.querySelector('div.ql-editor[contenteditable="true"], rich-textarea div[contenteditable="true"]');
            if (!editor) return { error: 'No Gemini editor found' };

            editor.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, '請只回覆兩個字：你好');
            editor.dispatchEvent(new Event('input', { bubbles: true }));

            // Look for send button after input event
            setTimeout(() => {
                const sendBtn = document.querySelector('button.send-button, button[aria-label*="傳送"], button[aria-label*="Send"], button.send-button-container');
                if (sendBtn && !sendBtn.disabled) {
                    sendBtn.click();
                } else {
                    editor.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
                }
            }, 300);

            return {
                editor_class: editor.className,
                editor_text: editor.innerText
            };
        """)
        print("Gemini Input Result:\n", json.dumps(send_res, indent=2, ensure_ascii=False))

        print("\nObserving Gemini response for 12 seconds...")
        for i in range(12):
            time.sleep(1)
            poll = driver.execute_script("""
                const responses = Array.from(document.querySelectorAll('message-content, model-response, div.model-response-text, div.markdown'));
                const texts = responses.map(r => r.innerText.trim()).filter(t => t.length > 0);
                return {
                    count: responses.length,
                    texts: texts.slice(-2)
                };
            """)
            print(f"[{i+1}s] Gemini Responses Count: {poll['count']}, Texts: {poll['texts']}")
            if any('你好' in t for t in poll['texts']) and i > 2:
                print("\n🎉🎉🎉 SUCCESS: Gemini Web response generated and verified!")
                break

    finally:
        driver.quit()

if __name__ == "__main__":
    test_gemini_interaction()
