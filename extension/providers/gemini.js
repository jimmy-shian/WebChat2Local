/**
 * WebChat2Local - Dedicated Google Gemini Provider
 */
const GeminiProvider = {
  name: "Gemini",

  isMatch: function () {
    return window.location.hostname.includes("gemini.google.com");
  },

  getUserInfo: async function () {
    return {
      email: "Google Gemini Web 用戶",
      plan: "Gemini Free / Advanced",
      provider: "Gemini",
    };
  },

  setInput: function (promptText) {
    const editor =
      document.querySelector("div.ql-editor[contenteditable='true']") ||
      document.querySelector("rich-textarea div[contenteditable='true']") ||
      document.querySelector("div[contenteditable='true']");

    if (!editor) throw new Error("找不到 Gemini 輸入框，請確認網頁已載入。");

    editor.focus();
    document.execCommand("selectAll", false, null);
    document.execCommand("insertText", false, promptText);
    editor.dispatchEvent(new Event("input", { bubbles: true }));
    return editor;
  },

  submit: function (editor) {
    const sendBtn =
      document.querySelector("button.send-button") ||
      document.querySelector("button[aria-label*='傳送']") ||
      document.querySelector("button[aria-label*='Send']") ||
      document.querySelector("button.send-button-container");

    if (sendBtn && !sendBtn.disabled) {
      sendBtn.click();
      console.log("[GeminiProvider] Send button clicked.");
    } else if (editor) {
      editor.dispatchEvent(
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
      document.querySelector("button[aria-label*='停止']") ||
      document.querySelector("button[aria-label*='Stop']");
    return !!stopBtn;
  },

  extractResponse: function (promptSnippet) {
    // Specifically target the inner content panel of message-content, NOT outer model-response wrapper
    const messageContents = Array.from(document.querySelectorAll("message-content, [id^='message-content-id-']"));

    let target = null;
    for (let i = messageContents.length - 1; i >= 0; i--) {
      const el = messageContents[i];
      const text = (el.innerText || "").trim();
      if (text.length > 0 && (!promptSnippet || !text.includes(promptSnippet))) {
        target = el;
        break;
      }
    }

    if (!target) {
      // Fallback to markdown panels
      const mdPanels = Array.from(document.querySelectorAll("div.markdown, div.model-response-text"));
      for (let i = mdPanels.length - 1; i >= 0; i--) {
        const text = (mdPanels[i].innerText || "").trim();
        if (text.length > 0 && (!promptSnippet || !text.includes(promptSnippet))) {
          target = mdPanels[i];
          break;
        }
      }
    }

    if (!target) return "";

    const mdEl = target.querySelector(".markdown") || target;
    return window.WebChat2LocalMarkdown.serialize(mdEl);
  },
};

if (typeof window !== "undefined") {
  window.GeminiProvider = GeminiProvider;
}
