import json
import os
import subprocess
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

EXTENSION_PATH = os.path.abspath(r"c:\Users\Administrator\Desktop\html_test\WebChat2Local\extension")

def run_step_by_step_debug():
    print("==================================================")
    print("[STEP-BY-STEP DOM & EXTENSION INSPECTOR]")
    print("==================================================")

    # 1. Start WebChat2Local server
    server_proc = subprocess.Popen(
        [sys.executable, "run_server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8"
    )
    time.sleep(2)

    options = Options()
    options.add_argument(f"--load-extension={EXTENSION_PATH}")
    options.add_argument("--disable-gpu")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get("https://chatgpt.com")
        time.sleep(6)

        # 1. Inspect Input Element in ChatGPT
        print("\n[Step 1] Inspecting Input Element:")
        inspect_script = """
        const textarea = document.querySelector('#prompt-textarea');
        const editable = document.querySelector('div[contenteditable="true"]');
        const sendBtn = document.querySelector('button[data-testid="send-button"]') || document.querySelector('button[aria-label*="Send"]');
        return {
            textarea_found: !!textarea,
            textarea_tag: textarea ? textarea.tagName : null,
            editable_found: !!editable,
            send_btn_found: !!sendBtn,
            send_btn_disabled: sendBtn ? sendBtn.disabled : null,
            badge_status: window.WebChat2LocalBridge ? window.WebChat2LocalBridge.status : 'undefined'
        };
        """
        dom_status = driver.execute_script(inspect_script)
        print("DOM Elements Status:", json.dumps(dom_status, indent=2))

        # 2. Test typing & sending directly via JS
        print("\n[Step 2] Testing Typing & Clicking Send via JavaScript:")
        send_script = """
        const input = document.querySelector('#prompt-textarea') || document.querySelector('div[contenteditable="true"]');
        if (!input) return { success: false, reason: 'No input element' };
        
        input.focus();
        document.execCommand('selectAll', false, null);
        document.execCommand('insertText', false, '請回覆：測試成功');
        input.dispatchEvent(new Event('input', { bubbles: true }));
        
        const sendBtn = document.querySelector('button[data-testid="send-button"]') || document.querySelector('button[aria-label*="Send"]');
        if (sendBtn) {
            sendBtn.click();
            return { success: true, clicked: true };
        } else {
            return { success: false, reason: 'No send button' };
        }
        """
        send_res = driver.execute_script(send_script)
        print("Send Test Result:", json.dumps(send_res, indent=2))

        # 3. Observe the generation for 15 seconds
        print("\n[Step 3] Polling DOM text every second for 15 seconds...")
        for i in range(15):
            time.sleep(1)
            poll_script = """
            const assistants = Array.from(document.querySelectorAll('[data-message-author-role="assistant"], article, div.markdown'));
            const last = assistants.length > 0 ? assistants[assistants.length - 1] : null;
            const stopBtn = document.querySelector('button[data-testid="stop-button"]');
            return {
                assistants_count: assistants.length,
                last_text: last ? (last.innerText || '').slice(0, 100) : '',
                stop_btn_present: !!stopBtn
            };
            """
            poll_res = driver.execute_script(poll_script)
            print(f"[{i+1}s] StopBtn: {poll_res['stop_btn_present']}, Text: '{poll_res['last_text']}'")
            if not poll_res['stop_btn_present'] and len(poll_res['last_text']) > 0 and i > 2:
                print("Generation complete detected in DOM!")
                break

        # 4. Check console logs
        print("\n--- Browser Console Logs ---")
        logs = driver.get_log("browser")
        for log in logs:
            if "WebChat2Local" in log.get("message", ""):
                print(f"[{log.get('level')}] {log.get('message')}")

    except Exception as e:
        print("[ERROR]", e)
    finally:
        if driver:
            driver.quit()
        if server_proc:
            server_proc.terminate()
            server_proc.kill()
        print("\nFinished.")

if __name__ == "__main__":
    run_step_by_step_debug()
