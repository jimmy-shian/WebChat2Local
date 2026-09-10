/**
 * WebChat2Local — ChatGPT 頁面診斷腳本
 * 用法：在 https://chatgpt.com 開啟 DevTools (F12) → Console → 貼上整檔 → Enter。
 * 把輸出的 JSON 貼回來，就能確定「GPT 網頁版到底要怎麼讀資料」。
 */
(function () {
  const out = { url: location.href, ts: new Date().toISOString() };

  // 1. 腳本載入狀態
  out.interceptorLoaded = !!window.__WebChat2Local_Chatgpt_Interceptor_Loaded;
  out.controllerLoaded = !!(window.ChatGptController || window.ChatGPTController);
  out.extractorLoaded = !!(window.ChatGptExtractor || window.ChatGPTExtractor);
  out.contentScript = out.controllerLoaded && out.extractorLoaded;

  // 2. 輸入框
  const editorSels = [
    "#prompt-textarea",
    "div#prompt-textarea[contenteditable='true']",
    "div[contenteditable='true'][role='textbox']",
    "div[contenteditable='true'][data-placeholder]",
    "textarea[data-id='root']",
    "textarea",
    "div[contenteditable='true']",
  ];
  out.editor = null;
  for (const sel of editorSels) {
    try {
      const el = document.querySelector(sel);
      if (el && el.offsetParent !== null) {
        out.editor = {
          selector: sel,
          tag: el.tagName,
          editable: el.isContentEditable,
          textLen: (el.innerText || el.value || "").length,
        };
        break;
      }
    } catch (e) { /* selector 不支援就跳過 */ }
  }

  // 3. 傳送按鈕
  const sendSels = [
    "button[data-testid='send-button']",
    "button[data-testid='stop-button']",
    "button[aria-label*='Send']",
    "button[aria-label*='傳送']",
    "form button",
  ];
  out.sendButton = null;
  out.stopVisible = false;
  for (const sel of sendSels) {
    try {
      const el = document.querySelector(sel);
      if (el && el.offsetParent !== null) {
        if (sel.includes("stop")) out.stopVisible = true;
        if (!out.sendButton && !sel.includes("stop")) {
          out.sendButton = {
            selector: sel,
            disabled: !!el.disabled,
            ariaDisabled: el.getAttribute("aria-disabled"),
            label: (el.getAttribute("aria-label") || "").slice(0, 40),
          };
        }
      }
    } catch (e) {}
  }
  out.isGenerating = out.stopVisible;

  // 4. 訊息元素（嚴格選擇器 + 寬鬆 fallback 各數一遍）
  function count(sel) {
    try { return document.querySelectorAll(sel).length; }
    catch (e) { return -1; }
  }
  out.assistantStrict = count("[data-message-author-role='assistant']");
  out.userStrict = count("[data-message-author-role='user']");
  out.messageIds = count("main [data-message-id]");
  out.articles = count("main article");
  out.markdowns = count("main .markdown, main [class*='markdown']");

  // 5. 最後一個疑似 assistant 元素的文字首 200 字
  out.lastAssistantHead = "";
  try {
    const els = document.querySelectorAll("[data-message-author-role='assistant']");
    if (els.length) {
      out.lastAssistantHead = (els[els.length - 1].innerText || "").replace(/\s+/g, " ").slice(0, 200);
    } else {
      const fb = document.querySelectorAll("main [data-message-id]");
      if (fb.length) {
        out.lastAssistantHead = (fb[fb.length - 1].innerText || "").replace(/\s+/g, " ").slice(0, 200);
      }
    }
  } catch (e) {}

  // 6. 錯誤橫幅
  out.errorBanner = "";
  try {
    const alerts = document.querySelectorAll("div[role='alert']");
    for (const a of alerts) {
      if (a.offsetParent !== null && (a.innerText || "").trim()) {
        out.errorBanner = a.innerText.trim().slice(0, 200);
        break;
      }
    }
  } catch (e) {}
  out.title = document.title;

  console.log("[W2L-DIAG] 請把下面整塊 JSON 貼回來：");
  console.log(JSON.stringify(out, null, 2));
  return out;
})();
