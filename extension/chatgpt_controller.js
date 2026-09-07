/**
 * ChatGPT Web DOM Controller
 * Handles prompt injection, modal dismissal, send button triggering,
 * and generation state detection on chatgpt.com (including unlogged-in guest mode).
 */

const ChatGptController = {
  findInputEditor: function () {
    const selectors = [
      "#prompt-textarea",
      "div#prompt-textarea[contenteditable='true']",
      "textarea#prompt-textarea",
      "div[contenteditable='true'][role='textbox']",
      "div[contenteditable='true'][data-placeholder]",
      "textarea[data-id='root']",
      "textarea[placeholder*='Message']",
      "textarea[placeholder*='傳送訊息']",
      "textarea[placeholder*='发送消息']",
      "textarea",
      "div[contenteditable='true']"
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.offsetParent !== null && !el.disabled && el.getAttribute("aria-disabled") !== "true") {
        return el;
      }
    }
    return null;
  },

  dismissLoginModals: function () {
    let dismissed = false;
    try {
      // 1. "Stay logged out" / "保持登出" buttons or links
      const stayLoggedOutKeywords = [
        "stay logged out",
        "保持登出",
        "繼續保持登出",
        "继续保持登出",
        "not now",
        "稍後再說",
        "稍后再说",
        "close",
        "關閉",
        "关闭"
      ];

      const candidates = document.querySelectorAll(
        "button, a, div[role='button'], [data-testid*='close'], [data-testid*='dismiss']"
      );

      for (const el of candidates) {
        if (el.offsetParent === null) continue;
        const text = (el.innerText || el.textContent || "").trim().toLowerCase();
        const aria = (el.getAttribute("aria-label") || "").trim().toLowerCase();
        
        if (stayLoggedOutKeywords.some(k => text === k || text.includes(k) || aria.includes(k))) {
          // Avoid clicking "Log in" / "Sign up" buttons!
          if (text.includes("log in") || text.includes("sign up") || text.includes("登入") || text.includes("註冊")) {
            continue;
          }
          console.log("[ChatGpt Bridge] Auto-dismissing modal/prompt:", text || aria);
          el.click();
          dismissed = true;
        }
      }

      // 2. Dialog backdrop close buttons
      const dialogCloseBtns = document.querySelectorAll(
        "div[role='dialog'] button[aria-label*='Close'], div[role='dialog'] button[aria-label*='關閉'], [data-state='open'] button[aria-label*='Close']"
      );
      for (const btn of dialogCloseBtns) {
        if (btn.offsetParent !== null) {
          btn.click();
          dismissed = true;
        }
      }
    } catch (e) {
      console.warn("[ChatGpt Bridge] Error while dismissing modals:", e);
    }
    return dismissed;
  },

  waitForIdleAndReady: async function (maxWaitMs = 6000) {
    const start = Date.now();
    while (Date.now() - start < maxWaitMs) {
      this.dismissLoginModals();
      const generating = this.isGenerating();
      const editor = this.findInputEditor();
      const ready = !generating && editor && editor.offsetParent !== null && !editor.disabled;
      if (ready) {
        await new Promise(r => setTimeout(r, 150));
        return editor;
      }
      await new Promise(r => setTimeout(r, 100));
    }
    return this.findInputEditor();
  },

  setInputText: function (promptText) {
    this.dismissLoginModals();
    const editor = this.findInputEditor();
    if (!editor) {
      throw new Error("找不到 ChatGPT 輸入框 (#prompt-textarea)，請確認網頁已完整載入。");
    }

    try { editor.focus(); } catch (_) {}

    if (editor.isContentEditable || editor.getAttribute("contenteditable") === "true") {
      editor.innerHTML = "";
      const p = document.createElement("p");
      p.textContent = promptText;
      editor.appendChild(p);

      if ((editor.innerText || editor.textContent || "").trim().length === 0) {
        editor.textContent = promptText;
      }

      try {
        editor.dispatchEvent(new InputEvent("beforeinput", {
          bubbles: true,
          cancelable: true,
          inputType: "insertText",
          data: promptText,
        }));
        editor.dispatchEvent(new InputEvent("input", {
          bubbles: true,
          inputType: "insertText",
          data: promptText,
        }));
      } catch (_) {}
    } else {
      // React 16+ native value setter bypass
      try {
        const proto = Object.getPrototypeOf(editor);
        const valueSetter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
        if (valueSetter) {
          valueSetter.call(editor, promptText);
        } else {
          editor.value = promptText;
        }
      } catch (_) {
        editor.value = promptText;
      }

      try {
        editor.dispatchEvent(new Event("input", { bubbles: true }));
        editor.dispatchEvent(new Event("change", { bubbles: true }));
      } catch (_) {}
    }

    return editor;
  },

  findSendButton: function () {
    const sendSelectors = [
      "button[data-testid='send-button']",
      "button[aria-label*='Send prompt']",
      "button[aria-label*='Send']",
      "button[aria-label*='傳送']",
      "button[aria-label*='发送']",
      "button.mb-1.mr-1:has(svg)",
      "form button:has(svg)"
    ];

    for (const sel of sendSelectors) {
      try {
        const btn = document.querySelector(sel);
        if (btn && btn.offsetParent !== null) {
          return btn;
        }
      } catch (_) {}
    }
    return null;
  },

  waitForSendButtonAndClick: async function (editor, maxWaitMs = 3500) {
    const start = Date.now();
    while (Date.now() - start < maxWaitMs) {
      const btn = this.findSendButton();
      if (btn && !btn.disabled && btn.getAttribute("aria-disabled") !== "true") {
        btn.click();
        return true;
      }
      await new Promise(r => setTimeout(r, 60));
    }

    // Fallback: click whatever send button is found
    const btn = this.findSendButton();
    if (btn) {
      btn.click();
      return true;
    }

    // Secondary fallback: Enter key event on editor
    if (editor) {
      editor.dispatchEvent(new KeyboardEvent("keydown", {
        key: "Enter",
        code: "Enter",
        keyCode: 13,
        which: 13,
        bubbles: true,
        cancelable: true,
      }));
      return true;
    }
    return false;
  },

  submitPromptWithRetry: async function (promptText) {
    await this.waitForIdleAndReady(6000);
    const editor = this.setInputText(promptText);
    await new Promise(r => setTimeout(r, 100));

    const sent = await this.waitForSendButtonAndClick(editor, 3500);
    if (!sent) {
      throw new Error("找不到或無法觸發 ChatGPT 傳送按鈕，請確認網頁狀態。");
    }

    await new Promise(r => setTimeout(r, 250));
    return editor;
  },

  isGenerating: function () {
    const stopSelectors = [
      "button[data-testid='stop-button']",
      "button[aria-label*='Stop generating']",
      "button[aria-label*='停止生成']",
      "button[aria-label='Stop']",
      ".result-streaming",
      "[data-is-streaming='true']",
      ".streaming-cursor"
    ];

    for (const sel of stopSelectors) {
      try {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null && !el.disabled && el.getAttribute("aria-disabled") !== "true") {
          return true;
        }
      } catch (_) {}
    }

    return false;
  },

  startNewChatIfAvailable: function () {
    const newChatSelectors = [
      "a[href='/']",
      "a[data-testid='create-new-chat-button']",
      "button[aria-label*='New chat']",
      "button[aria-label*='新對話']",
      "button[aria-label*='新建对话']",
      "a[aria-label*='New chat']"
    ];

    for (const sel of newChatSelectors) {
      const btn = document.querySelector(sel);
      if (btn && btn.offsetParent !== null) {
        btn.click();
        return true;
      }
    }

    // Direct navigation if button not in DOM
    if (window.location.pathname !== "/") {
      window.location.href = "https://chatgpt.com/";
      return true;
    }
    return false;
  },

  reloadPageCleanly: function () {
    console.log("[ChatGpt Bridge] Reloading page to wipe guest session memory...");
    if (window.location.pathname !== "/") {
      window.location.href = "https://chatgpt.com/";
    } else {
      window.location.reload();
    }
  }
};

if (typeof window !== "undefined") {
  window.ChatGptController = ChatGptController;
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = ChatGptController;
}
