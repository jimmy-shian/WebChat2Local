import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

EXTENSION_PATH = os.path.abspath(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension")

def test_v3_gemini_and_chatgpt_modular():
    print("==================================================")
    print("🚀 [TEST MODULAR v3.0.0 INTEGRATION]")
    print("==================================================")

    options = Options()
    options.add_argument(f"--load-extension={EXTENSION_PATH}")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    
    driver = webdriver.Chrome(options=options)
    try:
        # 1. Test on Gemini Web
        print("\n[1/2] 正在驗證 Google Gemini 模組化引擎...")
        driver.get("https://gemini.google.com/app?hl=zh-TW")
        time.sleep(6)

        gemini_check = driver.execute_script("""
            return {
                hasMarkdownUtil: typeof window.WebChat2LocalMarkdown !== 'undefined',
                hasGeminiProvider: typeof window.GeminiProvider !== 'undefined',
                isGeminiMatch: window.GeminiProvider ? window.GeminiProvider.isMatch() : false
            };
        """)
        print("Gemini Module Status:", json.dumps(gemini_check, indent=2))
        assert gemini_check["hasMarkdownUtil"], "Markdown util loaded"
        assert gemini_check["hasGeminiProvider"], "GeminiProvider loaded"
        assert gemini_check["isGeminiMatch"], "Gemini is matched"

        # 2. Test on ChatGPT Web
        print("\n[2/2] 正在驗證 ChatGPT 模組化引擎...")
        driver.get("https://chatgpt.com")
        time.sleep(6)

        chatgpt_check = driver.execute_script("""
            return {
                hasMarkdownUtil: typeof window.WebChat2LocalMarkdown !== 'undefined',
                hasChatGPTProvider: typeof window.ChatGPTProvider !== 'undefined',
                isChatGPTMatch: window.ChatGPTProvider ? window.ChatGPTProvider.isMatch() : false
            };
        """)
        print("ChatGPT Module Status:", json.dumps(chatgpt_check, indent=2))
        assert chatgpt_check["hasMarkdownUtil"], "Markdown util loaded"
        assert chatgpt_check["hasChatGPTProvider"], "ChatGPTProvider loaded"
        assert chatgpt_check["isChatGPTMatch"], "ChatGPT is matched"

        print("\n" + "="*50)
        print("🎉🎉🎉 [驗證成功] v3.0.0 模組化架構在 Gemini 與 ChatGPT 均完全載入且正確匹配！")
        print("="*50)

    finally:
        driver.quit()

if __name__ == "__main__":
    test_v3_gemini_and_chatgpt_modular()
