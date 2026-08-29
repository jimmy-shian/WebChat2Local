import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def test_tool_calling_prompt():
    print("==================================================")
    print("🚀 [TEST CHATGPT EMITTING WRITE_TO_FILE ACTION TOOL]")
    print("==================================================")

    options = Options()
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://chatgpt.com")
        time.sleep(6)

        # Construct the high-precision tool calling prompt
        tools_def = [
            {"name": "write_to_file", "params": ["path", "content"], "desc": "Write content to a file at the specified path."},
            {"name": "read_file", "params": ["path"], "desc": "Read the contents of a file."},
            {"name": "execute_command", "params": ["command"], "desc": "Execute a CLI command on Windows."},
            {"name": "attempt_completion", "params": ["result"], "desc": "Report completion of task."}
        ]

        tool_schemas = """
【可用本地工具與 XML 呼叫格式】
1. 建立或寫入檔案：
<write_to_file>
<path>檔案路徑</path>
<content>檔案內容</content>
</write_to_file>

2. 讀取檔案：
<read_file>
<path>檔案路徑</path>
</read_file>

3. 執行指令：
<execute_command>
<command>執行的命令</command>
</execute_command>

4. 任務全部完成回報：
<attempt_completion>
<result>完成說明</result>
</attempt_completion>

【絕對規則】
- 若使用者要求新增/編輯檔案、執行指令或讀取檔案，你【必須】輸出對應的動作工具標籤（如 <write_to_file>、<execute_command> 或 <read_file>），【絕對禁止】在動作未執行前就輸出 <attempt_completion>！
- 不要輸出多餘的聊天客套話，直接輸出工具標籤。
""".strip()

        user_prompt = f"{tool_schemas}\n\n[User Request]:\n新增一個 \"New.txt\"，內容寫 \"Hello World\""

        # Type and submit into ChatGPT Web
        driver.execute_script(f"""
            const textarea = document.querySelector('textarea, #mobile-composer-prompt, #prompt-textarea');
            if (textarea) {{
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
                if (nativeSetter) nativeSetter.call(textarea, {json.dumps(user_prompt)});
                textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                setTimeout(() => {{
                    const btn = document.querySelector('button.wm-composer-submitButton, button[type="submit"]');
                    if (btn) btn.click();
                }}, 300);
            }}
        """)

        print("Observing ChatGPT response for 15s...")
        for i in range(15):
            time.sleep(1)
            res = driver.execute_script("""
                const turn = document.querySelector('[data-message-author-role="assistant"], article:last-of-type, div.markdown');
                return turn ? (turn.innerText || turn.textContent || '') : '';
            """)
            if "<write_to_file>" in res:
                print(f"\n[{i+1}s] ChatGPT Response:\n", res)
                assert "<path>New.txt</path>" in res or "New.txt" in res
                assert "<content>Hello World</content>" in res or "Hello World" in res
                print("\n🎉🎉🎉 SUCCESS: ChatGPT Web correctly emitted <write_to_file> action tool!")
                break
            else:
                print(f"[{i+1}s] Waiting for response... (current len: {len(res)})")

    finally:
        driver.quit()

if __name__ == "__main__":
    test_tool_calling_prompt()
