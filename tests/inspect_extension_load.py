import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

EXTENSION_PATH = os.path.abspath(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension")

def inspect_extension():
    options = Options()
    options.add_argument(f"--load-extension={EXTENSION_PATH}")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    
    driver = webdriver.Chrome(options=options)
    try:
        driver.get("https://chatgpt.com")
        time.sleep(5)

        # Check console logs
        logs = driver.get_log("browser")
        print(f"Browser Console Logs ({len(logs)} entries):")
        for l in logs:
            if "WebChat2Local" in l["message"] or "error" in l["message"].lower():
                print(" ", l["level"], l["message"][:200])

        badge = driver.execute_script("return document.getElementById('webchat2local-badge') !== null;")
        print("Badge in DOM:", badge)

    finally:
        driver.quit()

if __name__ == "__main__":
    inspect_extension()
