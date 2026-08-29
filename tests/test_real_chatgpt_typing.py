import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def test_direct_typing():
    options = Options()
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get("https://chatgpt.com")
        time.sleep(6)
        
        # Test typing into all possible textareas
        res = driver.execute_script("""
            const textareas = Array.from(document.querySelectorAll('textarea'));
            const promptArea = textareas.find(t => t.id.includes('composer') || t.id.includes('prompt') || t.placeholder || t.className.includes('composer')) || textareas[0];
            
            if (!promptArea) return { error: 'No textarea found', count: textareas.length };
            
            promptArea.focus();
            promptArea.value = '請只回覆兩個字：你好';
            promptArea.dispatchEvent(new Event('input', { bubbles: true }));
            promptArea.dispatchEvent(new Event('change', { bubbles: true }));
            
            // Look for send button near composer
            const buttons = Array.from(document.querySelectorAll('button'));
            const sendBtn = buttons.find(b => {
                const label = (b.getAttribute('aria-label') || '').toLowerCase();
                const testid = (b.getAttribute('data-testid') || '').toLowerCase();
                return label.includes('send') || label.includes('發送') || label.includes('傳送') || testid.includes('send') || b.querySelector('svg');
            });
            
            let clicked = false;
            if (sendBtn && !sendBtn.disabled) {
                sendBtn.click();
                clicked = true;
            } else {
                promptArea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
            }
            
            return {
                prompt_id: promptArea.id,
                prompt_class: promptArea.className,
                button_clicked: clicked,
                button_label: sendBtn ? sendBtn.getAttribute('aria-label') : null
            };
        """)
        print("Typing result:\n", json.dumps(res, indent=2, ensure_ascii=False))
        
        print("Waiting 10 seconds for ChatGPT to generate response...")
        for i in range(10):
            time.sleep(1)
            poll = driver.execute_script("""
                // Check all possible response containers
                const bodyText = document.body.innerText;
                const articles = Array.from(document.querySelectorAll('article, div[data-message-author-role="assistant"], div[class*="agent-turn"], div[class*="message"]'));
                const last = articles.length > 0 ? articles[articles.length - 1].innerText : '';
                return {
                    has_hello: bodyText.includes('你好'),
                    last_article: last.slice(0, 150),
                    body_snippet: bodyText.slice(-300)
                };
            """)
            print(f"[{i+1}s] Found '你好': {poll['has_hello']}, Last Article: '{poll['last_article']}'")
            if poll['has_hello']:
                print("SUCCESS: ChatGPT responded with '你好'!")
                break
                
    finally:
        driver.quit()

if __name__ == "__main__":
    test_direct_typing()
