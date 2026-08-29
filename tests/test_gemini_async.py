import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def test_gemini_async_submit():
    print("==================================================")
    print("🚀 [TEST GEMINI ASYNC SUBMISSION & EXTRACTION]")
    print("==================================================")

    options = Options()
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)

    try:
        with open(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension\utils\markdown.js", "r", encoding="utf-8") as f:
            md_js = f.read()

        with open(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension\providers\gemini.js", "r", encoding="utf-8") as f:
            gemini_js = f.read()

        driver.get("https://gemini.google.com/app?hl=zh-TW")
        time.sleep(6)

        driver.execute_script(md_js)
        driver.execute_script(gemini_js)

        # Set input, wait for button activation, then submit
        driver.execute_script("""
            window.GeminiProvider.setInput('請只回覆：<attempt_completion><result>成功</result></attempt_completion>');
            setTimeout(() => {
                const editor = document.querySelector('div.ql-editor');
                window.GeminiProvider.submit(editor);
            }, 350);
        """)

        print("Observing Gemini for 12 seconds...")
        for i in range(12):
            time.sleep(1)
            poll = driver.execute_script("""
                const res = window.GeminiProvider.extractResponse('請只回覆');
                const isGen = window.GeminiProvider.isGenerating();
                return { res: res, isGen: isGen };
            """)
            print(f"[{i+1}s] isGen: {poll['isGen']}, Response: '{poll['res']}'")
            if "<attempt_completion>" in poll['res'] and "<result>" in poll['res']:
                print("\n🎉🎉🎉 [VERIFIED] Gemini response extracted with 100% intact <attempt_completion><result> tags!")
                break

    finally:
        driver.quit()

if __name__ == "__main__":
    test_gemini_async_submit()
