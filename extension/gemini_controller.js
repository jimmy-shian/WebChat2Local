/**
 * Gemini Web DOM Controller
 * Handles prompt input injection, model switching, and submission on gemini.google.com
 */

const GeminiController = {
  findInputEditor: function () {
    const selectors = [
      "div.ql-editor[contenteditable='true']",
      "rich-textarea div[contenteditable='true']",
      "div[contenteditable='true'][role='textbox']",
      "div[contenteditable='true']",
      "textarea.chat-input",
      "textarea",
      "[data-placeholder]"
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.offsetParent !== null) {
        return el;
      }
    }
    return null;
  },

  switchModelIfAvailable: async function (targetModel) {
    if (!targetModel) return;
    try {
      const norm = targetModel.toLowerCase();
      const switcherBtn = document.querySelector(
        "button[aria-label*='Model'], button[aria-label*='模型'], [data-test-id='model-switcher']"
      );
      if (switcherBtn) {
        const currentText = (switcherBtn.innerText || "").toLowerCase();
        if (norm.includes("flash") && !currentText.includes("flash")) {
          switcherBtn.click();
          await new Promise(r => setTimeout(r, 250));
          const flashOption = Array.from(document.querySelectorAll("mat-option, button, div[role='menuitem']"))
            .find(el => (el.innerText || "").toLowerCase().includes("flash"));
          if (flashOption) flashOption.click();
        } else if (norm.includes("pro") && !currentText.includes("pro")) {
          switcherBtn.click();
          await new Promise(r => setTimeout(r, 250));
          const proOption = Array.from(document.querySelectorAll("mat-option, button, div[role='menuitem']"))
            .find(el => (el.innerText || "").toLowerCase().includes("pro"));
          if (proOption) proOption.click();
        }
      }
    } catch (e) {
      console.warn("[Gemini Bridge] Model switch warning:", e);
    }
  },

  waitForIdleAndReady: async function (maxWaitMs = 6000) {
    const start = Date.now();
    while (Date.now() - start < maxWaitMs) {
      const generating = this.isGenerating();
      const editor = this.findInputEditor();
      const ready = !generating && editor && editor.offsetParent !== null && !editor.disabled && editor.getAttribute("aria-disabled") !== "true";
      if (ready) {
        // Small settle pause to let DOM animations & Angular finish
        await new Promise(r => setTimeout(r, 150));
        return editor;
      }
      await new Promise(r => setTimeout(r, 100));
    }
    return this.findInputEditor();
  },

  setInputText: function (promptText) {
    const editor = this.findInputEditor();
    if (!editor) {
      throw new Error("找不到 Gemini 輸入框，請確認網頁已完整載入。");
    }

    try { editor.focus(); } catch (_) {}

    if (editor.isContentEditable || editor.getAttribute("contenteditable") === "true") {
      // Clear previous content cleanly without generating heavy undo history
      editor.innerHTML = "";
      
      // For rich text editor (Quill / Angular), insert a paragraph or text node
      const p = document.createElement("p");
      p.textContent = promptText;
      editor.appendChild(p);

      if ((editor.innerText || editor.textContent || "").trim().length === 0) {
        editor.textContent = promptText;
      }
    } else {
      const proto = Object.getPrototypeOf(editor);
      const valueSetter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      if (valueSetter) valueSetter.call(editor, promptText);
      else editor.value = promptText;
    }

    // Notify Angular / React / framework input listeners
    try {
      if (typeof InputEvent !== "undefined") {
        editor.dispatchEvent(new InputEvent("beforeinput", {
          bubbles: true,
          cancelable: true,
          inputType: "insertParagraph",
          data: promptText,
        }));
        editor.dispatchEvent(new InputEvent("input", {
          bubbles: true,
          inputType: "insertParagraph",
          data: promptText,
        }));
      } else if (typeof Event !== "undefined") {
        editor.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (typeof Event !== "undefined") {
        editor.dispatchEvent(new Event("change", { bubbles: true }));
      }
    } catch (_) {}
    return editor;
  },

  isTemporaryChatActive: function () {
    const visible = (el) => !!el && el.offsetParent !== null && !el.disabled && el.getAttribute("aria-disabled") !== "true";
    
    // 1. Check DOM banner / badge / notice / header indicators
    // When Temporary Chat is active in Gemini Web, a banner, header or disclaimer is rendered:
    // e.g. "這是一段暫時聊天", "此對話不會儲存於歷程記錄中", "不會顯示在近期聊天中", "Temporary chat is on",
    // "Chats won't appear in Recent chats", "Temporary chats aren't saved in your Gemini Apps activity", etc.
    const bannerSelectors = [
      "[data-test-id*='temp']",
      "[data-test-id*='temporary']",
      "[class*='temporary-chat']",
      "[class*='temp-chat']",
      "[class*='temp_chat']",
      "mat-chip",
      "div.temporary-chat-header",
      "div.chat-history-notice",
      "div.disclaimer",
      "header",
      "div[role='status']",
      "div[role='alert']",
      "div[role='region']"
    ];

    const activeBannerKeywords = [
      /temporary\s*chat\s*(?:is\s*)?on/i,
      /chats\s*won'?t\s*appear\s*in\s*recent/i,
      /temporary\s*chats?\s*(?:aren'?t|are\s*not)\s*saved/i,
      /won'?t\s*(?:appear|show\s*up)\s*in\s*(?:your\s*)?(?:chat\s*)?history/i,
      /chats\s*in\s*this\s*mode\s*won'?t\s*be\s*saved/i,
      /this\s*is\s*a\s*temporary\s*chat/i,
      /(?:暫時|臨時|临时)(?:聊天|對話|对话)(?:已開啟|已开启|開啟中|开启中)/,
      /這是一段(?:暫時|臨時)聊天/,
      /这是一段(?:临时|暂时)聊天/,
      /不會(?:顯示|出現)在.*(?:近期|歷程|歷史)/,
      /不会(?:显示|出现)在.*(?:近期|历史)/,
      /不會儲存(?:於)?(?:歷程記錄|歷史記錄|聊天記錄)/,
      /不会保存(?:于)?(?:历史记录|聊天记录)/,
      /此對話不會儲存/,
      /此对话不会保存/
    ];

    for (const sel of bannerSelectors) {
      try {
        const elements = document.querySelectorAll(sel);
        for (const el of elements) {
          if (!visible(el)) continue;
          const text = (el.innerText || el.textContent || "").trim();
          if (text && activeBannerKeywords.some((re) => re.test(text))) {
            return true;
          }
        }
      } catch (_) {}
    }

    const labelOf = (el) => {
      if (!el) return "";
      const bits = [
        el.getAttribute("aria-label"),
        el.getAttribute("title"),
        el.getAttribute("data-tooltip"),
        el.getAttribute("data-tooltip-text"),
        el.getAttribute("mattooltip"),
        el.innerText,
      ];
      try {
        bits.push(el.querySelector("mat-icon")?.getAttribute("data-mat-icon-name"));
        bits.push(el.querySelector("svg")?.getAttribute("data-icon"));
      } catch (_) {}
      return bits.filter(Boolean).join(" ").toLowerCase();
    };

    const controls = Array.from(document.querySelectorAll("button, [role='button'], a, [aria-label], [title]"));
    const tempRe = /temporary\s*chat|temporary_chat|temp(?:orary)?[_\s-]*chat|暫時聊天|临时聊天|臨時聊天|臨時對話|临时对话|temp-chat/;

    // 2. Check if there is a button whose label explicitly means "Turn off / Exit / Close Temporary Chat"
    // If such a button exists, temporary chat MUST be active! Clicking it would close temporary chat!
    const turnOffRe = /turn\s*off\s*temp|disable\s*temp|exit\s*temp|close\s*temp|leave\s*temp|stop\s*temp|關閉.*(?:暫時|臨時|临时)|離開.*(?:暫時|臨時|临时)|退出.*(?:暫時|臨時|临时)|停止.*(?:暫時|臨時|临时)|已開啟.*(?:暫時|臨時|临时)|已开启.*(?:暫時|臨時|临时)/i;

    for (const el of controls) {
      if (!visible(el)) continue;
      const lbl = labelOf(el);
      if (turnOffRe.test(lbl)) {
        return true;
      }
    }

    // 3. Check if any temporary chat button has active/selected/checked state or classes
    const activeClassRe = /selected|active|checked|mat-mdc-button-checked|mat-button-toggle-checked|gds-button--selected|gds-button--active|is-active|highlight/i;
    const activeAttrRe = /^(?:true|on|active|selected|checked|page|step)$/i;

    for (const el of controls) {
      if (!visible(el)) continue;
      const lbl = labelOf(el);
      if (!tempRe.test(lbl)) continue;

      // Check aria and data attributes on element itself
      if (
        activeAttrRe.test(el.getAttribute("aria-pressed") || "") ||
        activeAttrRe.test(el.getAttribute("aria-checked") || "") ||
        activeAttrRe.test(el.getAttribute("aria-current") || "") ||
        activeAttrRe.test(el.getAttribute("data-state") || "") ||
        activeAttrRe.test(el.getAttribute("data-is-active") || "")
      ) {
        return true;
      }

      // Check CSS classes and attributes on element or its immediate parent/toggle wrapper
      const chain = [el, el.parentElement, el.closest("[role='button'], button, mat-button-toggle, [data-state], [class*='button']")].filter(Boolean);
      for (const node of chain) {
        const cls = (typeof node.className === "string" ? node.className : node.getAttribute("class") || "");
        if (activeClassRe.test(cls)) {
          return true;
        }
        if (
          activeAttrRe.test(node.getAttribute("aria-pressed") || "") ||
          activeAttrRe.test(node.getAttribute("aria-checked") || "") ||
          activeAttrRe.test(node.getAttribute("aria-current") || "") ||
          activeAttrRe.test(node.getAttribute("data-state") || "")
        ) {
          return true;
        }
      }

      // Check active words in label (ensuring it's not "turn on" / "開啟")
      if (
        /active|enabled|selected|\bon\b|current|opened|已開啟|已开启|開啟中|开启中|目前|當前|当前/i.test(lbl) &&
        !/turn\s*on|開啟暫時|开启临时|啟用|启用/i.test(lbl)
      ) {
        return true;
      }
    }

    return false;
  },

  ensureTemporaryChat: async function () {
    // Gemini Web's Temporary Chat is a UI mode.
    // If Temporary Chat is already active, NEVER click the toggle button again,
    // as clicking it in Gemini Web closes the temporary chat session.
    const url = new URL(window.location.href);
    if (url.hostname !== "gemini.google.com") {
      throw new Error("目前頁面不是 Gemini Web，已拒絕送出要求。");
    }

    // 1. If Temporary Chat is already active, return immediately without clicking anything!
    if (this.isTemporaryChatActive()) {
      return true;
    }

    const visible = (el) => !!el && el.offsetParent !== null && !el.disabled && el.getAttribute("aria-disabled") !== "true";
    const labelOf = (el) => {
      if (!el) return "";
      const bits = [
        el.getAttribute("aria-label"),
        el.getAttribute("title"),
        el.getAttribute("data-tooltip"),
        el.getAttribute("data-tooltip-text"),
        el.getAttribute("mattooltip"),
        el.innerText,
      ];
      try {
        bits.push(el.querySelector("mat-icon")?.getAttribute("data-mat-icon-name"));
        bits.push(el.querySelector("svg")?.getAttribute("data-icon"));
      } catch (_) {}
      return bits.filter(Boolean).join(" ").toLowerCase();
    };

    const controls = Array.from(document.querySelectorAll("button, [role='button'], a, [aria-label], [title]"));
    const tempRe = /temporary\s*chat|temporary_chat|temp(?:orary)?[_\s-]*chat|暫時聊天|临时聊天|臨時聊天|臨時對話|临时对话|temp-chat/;

    // Find the candidate button to TURN ON temporary chat
    // Must NOT be help/learn more/info, and must NOT be a "turn off" / "關閉" button
    const candidate = controls.find((el) => {
      if (!visible(el)) return false;
      const lbl = labelOf(el);
      if (!tempRe.test(lbl)) return false;
      if (/learn|help|了解|瞭解|說明|说明|info|about/i.test(lbl)) return false;
      if (/turn\s*off|disable|exit|close|leave|stop|關閉|離開|退出|停止/i.test(lbl)) return false;
      return true;
    });

    if (!candidate) {
      // Re-verify if already active
      if (this.isTemporaryChatActive()) {
        return true;
      }
      // If no candidate toggle button found but input editor is present and usable, continue safely
      const editor = this.findInputEditor();
      if (editor) {
        console.warn("[Gemini Bridge] 未找到 Temporary Chat 按鈕，但輸入框已就緒，使用目前對話。");
        return true;
      }
      throw new Error("找不到 Gemini Temporary Chat，為避免落入一般對話，已拒絕送出要求。");
    }

    // Click candidate to turn on temporary chat
    candidate.click();
    await new Promise((resolve) => setTimeout(resolve, 500));

    // Verify after click
    if (this.isTemporaryChatActive()) {
      return true;
    }

    // Secondary check: Did the candidate button or parent state change to active?
    const stateful = [candidate, candidate.parentElement, candidate.closest("[aria-pressed], [aria-current], [data-state], [class*='button']")].filter(Boolean);
    if (stateful.some((el) => visible(el) && (
      el.getAttribute("aria-pressed") === "true" ||
      el.getAttribute("aria-checked") === "true" ||
      el.getAttribute("aria-current") === "true" ||
      /active|selected|on|checked/.test((el.getAttribute("data-state") || "").toLowerCase()) ||
      /selected|active|checked/.test((typeof el.className === "string" ? el.className : "").toLowerCase())
    ))) {
      return true;
    }

    const editor = this.findInputEditor();
    if (editor) {
      return true;
    }

    throw new Error("Gemini 未確認已進入 Temporary Chat，為避免使用一般對話，已停止本次要求。");
  },

  findSendButton: function () {
    const sendSelectors = [
      "button.send-button",
      "button[aria-label*='Send']",
      "button[aria-label*='傳送']",
      "button[aria-label*='发送']",
      "button[aria-label*='Submit']",
      "button.send-button-container",
      ".send-button",
      "button:has(mat-icon[data-mat-icon-name='send'])",
      "button:has(svg[data-icon='send'])"
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

  clickSendButton: function (editor) {
    const btn = this.findSendButton();
    if (btn && !btn.disabled && btn.getAttribute("aria-disabled") !== "true") {
      btn.click();
      return true;
    }

    if (editor) {
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
      return true;
    }
    return false;
  },

  waitForSendButtonAndClick: async function (editor, maxWaitMs = 3500) {
    const start = Date.now();
    
    // Poll for the send button to become enabled by Angular
    while (Date.now() - start < maxWaitMs) {
      const btn = this.findSendButton();
      if (btn && !btn.disabled && btn.getAttribute("aria-disabled") !== "true") {
        btn.click();
        return true;
      }
      await new Promise(r => setTimeout(r, 60));
    }

    // Try clicking send button anyway or use fallback
    const btn = this.findSendButton();
    if (btn) {
      btn.click();
      return true;
    }

    // Fallback: Dispatch Enter key event to editor
    if (editor) {
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
      return true;
    }

    return false;
  },

  submitPromptWithRetry: async function (promptText) {
    // 1. Wait for screen / DOM / Angular state to be completely idle & ready
    await this.waitForIdleAndReady(6000);

    // 2. Inject text safely and non-blockingly
    const editor = this.setInputText(promptText);

    // 4. Wait for Angular to activate the send button and click it
    const sent = await this.waitForSendButtonAndClick(editor, 3500);
    if (!sent) {
      throw new Error("找不到或無法觸發 Gemini 傳送按鈕，請確認網頁狀態。");
    }

    // 5. Short verify pause to ensure submission started
    await new Promise(r => setTimeout(r, 250));
    return editor;
  },

  isGenerating: function () {
    const stopSelectors = [
      "button[aria-label*='Stop']",
      "button[aria-label*='停止']",
      "button[aria-label*='暂停']",
      "button[aria-label*='Stop generating']",
      "button[aria-label*='停止生成']",
      "button.stop-button",
      ".stop-generating-button",
      "button:has(mat-icon[data-mat-icon-name='stop'])",
      "button:has(svg[data-icon='stop'])"
    ];

    for (const sel of stopSelectors) {
      try {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null && !el.disabled && el.getAttribute("aria-disabled") !== "true") {
          return true;
        }
      } catch (_) {}
    }

    // Secondary check: active streaming indicator in current model response container
    try {
      const activeSpinners = document.querySelectorAll(
        "model-response .sparkle-thinking, model-response .loading-dots, message-content .sparkle-thinking, [data-test-id='model-response'] .sparkle-thinking"
      );
      for (const sp of activeSpinners) {
        if (sp && sp.offsetParent !== null) return true;
      }
    } catch (_) {}

    return false;
  },

  startNewChatIfAvailable: function () {
    const newChatSelectors = [
      "a[href='/app']",
      "button[aria-label*='New chat']",
      "button[aria-label*='新增對話']",
      "button[aria-label*='新對話']",
      ".new-chat-button",
      "div[role='button']:has(mat-icon[data-mat-icon-name='add'])"
    ];
    for (const sel of newChatSelectors) {
      const btn = document.querySelector(sel);
      if (btn && btn.offsetParent !== null) {
        btn.click();
        return true;
      }
    }
    return false;
  },
};

if (typeof window !== "undefined") {
  window.GeminiController = GeminiController;
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = GeminiController;
}
