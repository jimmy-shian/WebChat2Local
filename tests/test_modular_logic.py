import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def test_modular_logic_directly():
    print("==================================================")
    print("🚀 [TEST MODULAR v3.0.0 LOGIC IN GEMINI & CHATGPT]")
    print("==================================================")

    options = Options()
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)

    try:
        # 1. Load Markdown Serializer Script
        with open(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension\utils\markdown.js", "r", encoding="utf-8") as f:
            md_js = f.read()

        # 2. Load Providers
        with open(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension\providers\gemini.js", "r", encoding="utf-8") as f:
            gemini_js = f.read()

        with open(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension\providers\chatgpt.js", "r", encoding="utf-8") as f:
            chatgpt_js = f.read()

        driver.get("https://gemini.google.com/app?hl=zh-TW")
        time.sleep(6)

        driver.execute_script(md_js)
        driver.execute_script(gemini_js)

        # Test Gemini Input & Extraction
        test_res = driver.execute_script("""
            const isMatch = window.GeminiProvider.isMatch();
            const input = window.GeminiProvider.setInput('請用 <attempt_completion><result>模組化測試成功</result></attempt_completion> 回覆我');
            window.GeminiProvider.submit(input);
            return { isMatch: isMatch, inputFound: !!input };
        """)
        print("Gemini Input Result:", json.dumps(test_res, indent=2))

        print("\nWaiting for Gemini response and verifying extraction...")
        for i in range(12):
            time.sleep(1)
            poll = driver.execute_script("""
                const isGen = window.GeminiProvider.isGenerating();
                const res = window.GeminiProvider.extractResponse('模組化測試成功');
                return { isGen: isGen, res: res };
            """)
            print(f"[{i+1}s] isGen: {poll['isGen']}, Response: '{poll['res']}'")
            if "<attempt_completion>" in poll['res'] and "<result>" in poll['res']:
                print("\n🎉🎉🎉 [SUCCESS] Gemini Provider successfully preserved <attempt_completion><result> tags!")
                break

    finally:
        driver.quit()

if __name__ == "__main__":
    test_modular_logic_directly()
