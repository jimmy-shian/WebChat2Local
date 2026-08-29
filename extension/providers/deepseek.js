/**
 * WebChat2Local - Dedicated DeepSeek Provider
 * Supports chat.deepseek.com (DeepSeek-V3, DeepSeek-R1)
 */
const DeepSeekProvider = {
  name: "DeepSeek",

  isMatch: function () {
    return window.location.hostname.includes("deepseek.com");
  },

  getUserInfo: async function () {
    try {
      const resp = await fetch("https://chat.deepseek.com/api/v0/users/current", {
        method: "GET",
        headers: { "Accept": "application/json" },
        credentials: "include",
      });
      if (resp.ok) {
        const data = await resp.json();
        if (data && data.data) {
          const user = data.data;
          return {
            email: user.email || user.name || "DeepSeek 已登入用戶",
            plan: "DeepSeek-V3 / R1 (Free Web)",
            provider: "DeepSeek",
          };
        }
      }
    } catch (e) {}

    return {
      email: "DeepSeek Web 用戶",
      plan: "DeepSeek-V3 / R1",
      provider: "DeepSeek",
    };
  },

  setInput: function (promptText) {
    const textarea =
      document.querySelector("textarea#chat-input") ||
      document.querySelector("textarea[placeholder*='DeepSeek']") ||
      document.querySelector("textarea[placeholder*='输入']") ||
      document.querySelector("textarea[placeholder*='Message']") ||
      document.querySelector("textarea") ||
      document.querySelector("div[contenteditable='true']");

    if (!textarea) throw new Error("找不到 DeepSeek 輸入框，請確認網頁已載入。");

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
    // DeepSeek send buttons can be div.ds-icon-button or button
    const submitBtn =
      document.querySelector("div[role='button'][aria-disabled='false']") ||
      document.querySelector("div.ds-icon-button:not([disabled])") ||
      document.querySelector("button[type='submit']:not([disabled])") ||
      document.querySelector("button[aria-label*='傳送']") ||
      document.querySelector("button[aria-label*='Send']") ||
      document.querySelector("button[aria-label*='发送']") ||
      document.querySelector("div[class*='send-button']") ||
      document.querySelector("div[class*='sendBtn']");

    if (submitBtn && !submitBtn.disabled && submitBtn.getAttribute("aria-disabled") !== "true") {
      submitBtn.click();
      console.log("[DeepSeekProvider] Submit button clicked.");
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
  },

  isGenerating: function () {
    const stopBtn =
      document.querySelector("div[aria-label*='停止']") ||
      document.querySelector("div[aria-label*='Stop']") ||
      document.querySelector("button[aria-label*='停止']") ||
      document.querySelector("button[aria-label*='Stop']") ||
      document.querySelector("div[class*='stop-button']") ||
      document.querySelector(".ds-icon-button svg rect");
    return !!stopBtn;
  },

  extractResponse: function (promptSnippet) {
    // Collect assistant message elements
    const candidates = Array.from(
      document.querySelectorAll(
        ".ds-markdown, div[class*='ds-markdown'], div[class*='chat-message'], div[class*='message-assistant'], div[class*='assistant']"
      )
    );

    const nonUser = candidates.filter((el) => {
      const isUser =
        el.getAttribute("data-message-author-role") === "user" ||
        el.closest("[class*='user-message']") ||
        el.closest("[class*='message-user']");
      const text = el.innerText || el.textContent || "";
      if (isUser) return false;
      if (promptSnippet && text.includes(promptSnippet)) return false;
      if (text.trim().length === 0) return false;
      return true;
    });

    if (nonUser.length === 0) return "";

    const target = nonUser[nonUser.length - 1];
    const mdEl = target.querySelector(".ds-markdown") || target.querySelector(".markdown") || target;
    return window.WebChat2LocalMarkdown.serialize(mdEl);
  },
};

if (typeof window !== "undefined") {
  window.DeepSeekProvider = DeepSeekProvider;
}
