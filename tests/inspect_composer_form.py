import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def inspect_composer_form():
    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get("https://chatgpt.com")
        time.sleep(6)
        
        info = driver.execute_script("""
            const form = document.querySelector('form');
            const textarea = document.querySelector('textarea, #prompt-textarea, [contenteditable="true"]');
            
            // Find all buttons inside or near form
            const formButtons = form ? Array.from(form.querySelectorAll('button')).map(b => ({
                text: b.innerText.trim(),
                ariaLabel: b.getAttribute('aria-label'),
                testid: b.getAttribute('data-testid'),
                className: b.className,
                disabled: b.disabled,
                type: b.type
            })) : [];
            
            // Find all buttons on entire page
            const allButtons = Array.from(document.querySelectorAll('button')).map(b => ({
                text: b.innerText.trim(),
                ariaLabel: b.getAttribute('aria-label'),
                testid: b.getAttribute('data-testid'),
                className: b.className,
                disabled: b.disabled
            }));
            
            return {
                form_found: !!form,
                textarea_found: !!textarea,
                textarea_id: textarea ? textarea.id : null,
                textarea_class: textarea ? textarea.className : null,
                form_buttons: formButtons,
                all_buttons_count: allButtons.length,
                all_buttons: allButtons
            };
        """)
        print("Composer & Buttons Info:\n", json.dumps(info, indent=2, ensure_ascii=False))
        
    finally:
        driver.quit()

if __name__ == "__main__":
    inspect_composer_form()
