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
    // 1. Primary precise selector on modern ChatGPT Web
    const assistantEls = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]'));
    if (assistantEls.length > 0) {
      const target = assistantEls[assistantEls.length - 1];
      const mdEl = target.querySelector(".markdown") || target.querySelector("[class*='markdown']") || target;
      const res = window.WebChat2LocalMarkdown ? window.WebChat2LocalMarkdown.serialize(mdEl) : (mdEl.innerText || mdEl.textContent || "");
      if (res && res.trim().length > 0) {
        return res.trim();
      }
    }

    // 2. Secondary fallback: articles that are not user role
    const articles = Array.from(document.querySelectorAll("article"));
    const nonUserArticles = articles.filter((el) => {
      const isUser = el.getAttribute("data-message-author-role") === "user" || el.querySelector('[data-message-author-role="user"]');
      return !isUser;
    });

    if (nonUserArticles.length > 0) {
      const target = nonUserArticles[nonUserArticles.length - 1];
      const mdEl = target.querySelector(".markdown") || target.querySelector("[class*='markdown']") || target;
      const res = window.WebChat2LocalMarkdown ? window.WebChat2LocalMarkdown.serialize(mdEl) : (mdEl.innerText || mdEl.textContent || "");
      if (res && res.trim().length > 0) {
        return res.trim();
      }
    }

    return "";
  },
};

if (typeof window !== "undefined") {
  window.ChatGPTProvider = ChatGPTProvider;
}
