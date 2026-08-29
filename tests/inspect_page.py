import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

EXTENSION_PATH = os.path.abspath(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension")
SCREENSHOT_PATH = os.path.abspath(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\tests\page_snapshot.png")

def inspect_page():
    options = Options()
    options.add_argument(f"--load-extension={EXTENSION_PATH}")
    options.add_argument("--disable-gpu")
    
    driver = webdriver.Chrome(options=options)
    try:
        driver.get("https://chatgpt.com")
        time.sleep(8)
        print("Page URL:", driver.current_url)
        print("Page Title:", driver.title)
        
        # Save screenshot
        driver.save_screenshot(SCREENSHOT_PATH)
        print(f"Screenshot saved to: {SCREENSHOT_PATH}")
        
        # Check all buttons, inputs, iframes
        info = driver.execute_script("""
            return {
                inputs: Array.from(document.querySelectorAll('input, textarea, [contenteditable]')).map(el => ({
                    tag: el.tagName,
                    id: el.id,
                    className: el.className,
                    contenteditable: el.getAttribute('contenteditable')
                })),
                buttons: Array.from(document.querySelectorAll('button')).map(b => ({
                    text: b.innerText.trim(),
                    ariaLabel: b.getAttribute('aria-label'),
                    testid: b.getAttribute('data-testid')
                })).slice(0, 10),
                iframes: document.querySelectorAll('iframe').length,
                bodySnippet: document.body.innerText.slice(0, 300)
            };
        """)
        print("Page Elements Info:\n", json.dumps(info, indent=2, ensure_ascii=False))

    finally:
        driver.quit()

if __name__ == "__main__":
    inspect_page()
