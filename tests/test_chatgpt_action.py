import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def test_chatgpt_real_action_tool():
    print("==================================================")
    print("🚀 [TEST CHATGPT REAL ACTION TOOL: WRITE_TO_FILE]")
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

        tool_schemas = """
【你必須使用的本地工具與 XML 格式】
1. 建立或寫入檔案：
<write_to_file>
<path>檔案路徑</path>
<content>檔案內容</content>
</write_to_file>

2. 任務全部完成：
<attempt_completion>
<result>說明</result>
</attempt_completion>

【規則】
若使用者要求新增檔案，你【必須】輸出 <write_to_file> 工具標籤。不要輸出客套前言。
""".strip()

        user_prompt = f"{tool_schemas}\n\n[使用者請求]:\n新增一個 \"New.txt\"，內容寫 \"Hello World\""

        # Set input, wait for button activation, then submit
        driver.execute_script(f"""
            window.ChatGPTProvider.setInput({json.dumps(user_prompt)});
            setTimeout(() => {{
                const textarea = document.querySelector('textarea, #prompt-textarea');
                window.ChatGPTProvider.submit(textarea);
            }}, 350);
        """)

        print("Observing ChatGPT response...")
        for i in range(15):
            time.sleep(1)
            poll = driver.execute_script("""
                const res = window.ChatGPTProvider.extractResponse('使用者請求');
                const isGen = window.ChatGPTProvider.isGenerating();
                return { res: res, isGen: isGen };
            """)
            print(f"[{i+1}s] isGen: {poll['isGen']}, Response (len {len(poll['res'])}): {poll['res'][:150]}")
            if "<write_to_file>" in poll['res']:
                print("\n" + "="*50)
                print("ChatGPT Full Generated Output:\n", poll['res'])
                assert "<path>New.txt</path>" in poll['res'] or "New.txt" in poll['res']
                assert "<content>Hello World</content>" in poll['res'] or "Hello World" in poll['res']
                print("🎉🎉🎉 VERIFIED: ChatGPT Web correctly emitted <write_to_file> action tool tag!")
                print("="*50)
                break

    finally:
        driver.quit()

if __name__ == "__main__":
    test_chatgpt_real_action_tool()
