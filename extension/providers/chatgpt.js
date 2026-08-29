/**
 * WebChat2Local - Dedicated ChatGPT Provider
 */
const ChatGPTProvider = {
  name: "ChatGPT",

  isMatch: function () {
    return window.location.hostname.includes("chatgpt.com");
  },

  getUserInfo: async function () {
    try {
      const resp = await fetch("https://chatgpt.com/api/auth/session", {
        method: "GET",
        headers: { "Accept": "application/json" },
        credentials: "include",
      });
      if (resp.ok) {
        const data = await resp.json();
        if (data && data.accessToken) {
          return {
            email: data.user?.email || "已登入用戶",
            plan: data.account?.plan_type || "ChatGPT Plus / Free",
            provider: "ChatGPT",
          };
        }
      }
    } catch (e) {}

    return {
      email: "ChatGPT 免登入免費版",
      plan: "Anonymous Free Tier",
      provider: "ChatGPT",
    };
  },

  setInput: function (promptText) {
    const textarea =
      document.querySelector("textarea.wm-composer-textarea") ||
      document.querySelector("#mobile-composer-prompt") ||
      document.querySelector("#prompt-textarea") ||
      document.querySelector("textarea") ||
      document.querySelector("div[contenteditable='true']");

    if (!textarea) throw new Error("找不到 ChatGPT 輸入框，請確認網頁已載入。");

    textarea.focus();
    if (textarea.tagName.toLowerCase() === "textarea" || textarea.tagName.toLowerCase() === "input") {
      const nativeSetter =
        Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set ||
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;

      if (nativeSetter) {
        nativeSetter.call(textarea, promptText);
      } else {
        textarea.value = promptText;
      }
    } else {
      document.execCommand("selectAll", false, null);
      document.execCommand("insertText", false, promptText);
    }

    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    textarea.dispatchEvent(new Event("change", { bubbles: true }));
    return textarea;
  },

  submit: function (textarea) {
    const submitBtn =
      document.querySelector("button.wm-composer-submitButton") ||
      document.querySelector("button[type='submit']") ||
      document.querySelector("button[aria-label*='傳送']") ||
      document.querySelector("button[aria-label*='Send']") ||
      document.querySelector("button[data-testid='send-button']");

    if (submitBtn && !submitBtn.disabled) {
      submitBtn.click();
      console.log("[ChatGPTProvider] Submit button clicked.");
    } else {
      const form = document.querySelector("form");
      if (form) {
        form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      } else if (textarea) {
        textarea.dispatchEvent(
          new KeyboardEvent("keydown", {
            key: "Enter",
            code: "Enter",
            keyCode: 13,
            which: 13,
            bubbles: true,
            cancelable: true,
          })
        );
      }
    }
  },

  isGenerating: function () {
    const stopBtn =
      document.querySelector("button[data-testid='stop-button']") ||
      document.querySelector("button[aria-label*='Stop']") ||
      document.querySelector("button[aria-label*='停止']");
    return !!stopBtn;
  },

  extractResponse: function (promptSnippet) {
    // Prefer precise assistant message containers; fall back to broader ones.
    const candidates = Array.from(
      document.querySelectorAll(
        '[data-message-author-role="assistant"], article, div[class*="agent-turn"], div[class*="message"]'
      )
    );

    // Garbage patterns: citation/source panels and UI chrome that are NOT the answer.
    const GARBAGE_RE = /資料來源|data-reference-detail-header|_sCvC0W_header/i;

    const nonUser = candidates.filter((el) => {
      const isUser =
        el.getAttribute("data-message-author-role") === "user" ||
        el.querySelector('[data-message-author-role="user"]');
      const text = el.innerText || el.textContent || "";
      if (isUser) return false;
      if (promptSnippet && text.includes(promptSnippet)) return false;
      if (text.trim().length === 0) return false;
      // Skip pure citation/source header panels.
      if (GARBAGE_RE.test(text) && text.trim().length < 200) return false;
      return true;
    });

    if (nonUser.length === 0) return "";

    const target = nonUser[nonUser.length - 1];
    const mdEl = target.querySelector(".markdown") || target.querySelector("[class*='markdown']") || target;
    const serialized = window.WebChat2LocalMarkdown.serialize(mdEl);

    // Final guard: if serialization produced only a garbage header, reject it.
    if (serialized && GARBAGE_RE.test(serialized) && serialized.replace(/<[^>]*>/g, "").trim().length < 50) {
      return "";
    }
    return serialized;
  },
};

if (typeof window !== "undefined") {
  window.ChatGPTProvider = ChatGPTProvider;
}
