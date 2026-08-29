import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def test_desktop_typing():
    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get("https://chatgpt.com")
        time.sleep(6)
        
        # Test finding desktop input and send button
        res = driver.execute_script("""
            // 1. Find all possible prompt elements
            const promptArea = document.querySelector('#prompt-textarea') ||
                               document.querySelector('div[contenteditable="true"]') ||
                               document.querySelector('textarea.wm-composer-textarea') ||
                               document.querySelector('textarea');
                               
            if (!promptArea) return { error: 'No prompt area found' };
            
            promptArea.focus();
            
            // Try DataTransfer paste
            const dt = new DataTransfer();
            dt.setData('text/plain', '請只回覆兩個字：你好');
            promptArea.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt }));
            
            if (!promptArea.textContent.includes('你好') && promptArea.value !== '請只回覆兩個字：你好') {
                document.execCommand('selectAll', false, null);
                document.execCommand('insertText', false, '請只回覆兩個字：你好');
            }
            if (promptArea.tagName.toLowerCase() === 'textarea') {
                promptArea.value = '請只回覆兩個字：你好';
            }
            promptArea.dispatchEvent(new Event('input', { bubbles: true }));
            promptArea.dispatchEvent(new Event('change', { bubbles: true }));
            
            // 2. Find send button
            const sendBtn = document.querySelector('button[data-testid="send-button"]') ||
                            document.querySelector('button[aria-label*="Send"]') ||
                            document.querySelector('button[aria-label*="發送"]') ||
                            document.querySelector('button[aria-label*="傳送"]');
                            
            let clicked = false;
            if (sendBtn && !sendBtn.disabled) {
                sendBtn.click();
                clicked = true;
            } else {
                promptArea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
            }
            
            return {
                prompt_tag: promptArea.tagName,
                prompt_id: promptArea.id,
                prompt_class: promptArea.className,
                send_btn_found: !!sendBtn,
                send_btn_disabled: sendBtn ? sendBtn.disabled : null,
                send_btn_testid: sendBtn ? sendBtn.getAttribute('data-testid') : null,
                clicked: clicked
            };
        """)
        print("Desktop typing result:\n", json.dumps(res, indent=2, ensure_ascii=False))
        
        print("\nObserving DOM for 15 seconds...")
        for i in range(15):
            time.sleep(1)
            poll = driver.execute_script("""
                const assistants = Array.from(document.querySelectorAll('[data-message-author-role="assistant"], article, div.markdown, div.prose, div[class*="agent-turn"]'));
                const textList = assistants.map(a => (a.innerText || '').trim()).filter(t => t.length > 0);
                const stopBtn = document.querySelector('button[data-testid="stop-button"]');
                return {
                    elements_count: assistants.length,
                    texts: textList.slice(-2),
                    stop_btn: !!stopBtn
                };
            """)
            print(f"[{i+1}s] StopBtn: {poll['stop_btn']}, Texts: {poll['texts']}")
            if any('你好' in t for t in poll['texts']) and not poll['stop_btn'] and i > 2:
                print("\n[SUCCESS] Response generated and captured in DOM!")
                break
                
    finally:
        driver.quit()

if __name__ == "__main__":
    test_desktop_typing()
