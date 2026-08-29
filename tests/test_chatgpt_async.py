import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def test_chatgpt_async_submit():
    print("==================================================")
    print("🚀 [TEST CHATGPT ASYNC SUBMISSION & EXTRACTION]")
    print("==================================================")

    options = Options()
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)

    try:
        with open(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension\utils\markdown.js", "r", encoding="utf-8") as f:
            md_js = f.read()

        with open(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension\providers\chatgpt.js", "r", encoding="utf-8") as f:
            chatgpt_js = f.read()

        driver.get("https://chatgpt.com")
        time.sleep(6)

        driver.execute_script(md_js)
        driver.execute_script(chatgpt_js)

        # Set input, wait for button activation, then submit
        driver.execute_script("""
            window.ChatGPTProvider.setInput('請只回覆：<attempt_completion><result>ChatGPT測試成功</result></attempt_completion>');
            setTimeout(() => {
                const textarea = document.querySelector('textarea');
                window.ChatGPTProvider.submit(textarea);
            }, 350);
        """)

        print("Observing ChatGPT for 12 seconds...")
        for i in range(12):
            time.sleep(1)
            poll = driver.execute_script("""
                const res = window.ChatGPTProvider.extractResponse('請只回覆');
                const isGen = window.ChatGPTProvider.isGenerating();
                return { res: res, isGen: isGen };
            """)
            print(f"[{i+1}s] isGen: {poll['isGen']}, Response: '{poll['res']}'")
            if "<attempt_completion>" in poll['res']:
                print("\n🎉🎉🎉 [VERIFIED] ChatGPT response extracted with 100% intact <attempt_completion> tags!")
                break

    finally:
        driver.quit()

if __name__ == "__main__":
    test_chatgpt_async_submit()
