import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def inspect_gemini_web():
    print("==================================================")
    print("🚀 [GEMINI WEB DOM INSPECTION]")
    print("==================================================")

    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://gemini.google.com/app?hl=zh-TW")
        time.sleep(6)

        print("Gemini URL:", driver.current_url)
        print("Gemini Title:", driver.title)

        info = driver.execute_script("""
            const inputs = Array.from(document.querySelectorAll('div.ql-editor, rich-textarea, div[contenteditable="true"], textarea, input')).map(el => ({
                tag: el.tagName,
                className: el.className,
                id: el.id,
                contenteditable: el.getAttribute('contenteditable'),
                ariaLabel: el.getAttribute('aria-label')
            }));

            const buttons = Array.from(document.querySelectorAll('button')).map(b => ({
                text: b.innerText.trim(),
                ariaLabel: b.getAttribute('aria-label'),
                className: b.className
            })).filter(b => b.ariaLabel || b.text);

            return {
                inputs: inputs,
                buttons_sample: buttons.slice(0, 15),
                bodySnippet: document.body.innerText.slice(0, 300)
            };
        """)
        print("Gemini DOM Info:\n", json.dumps(info, indent=2, ensure_ascii=False))

    finally:
        driver.quit()

if __name__ == "__main__":
    inspect_gemini_web()
