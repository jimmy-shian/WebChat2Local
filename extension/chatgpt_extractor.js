/**
 * ChatGPT Web Response Extractor
 * Extracts real-time streamed responses and reasoning blocks from chatgpt.com DOM
 * with bulletproof multi-selector fallback and strict turn isolation.
 */

const ChatGptExtractor = {
  _priorElements: new Set(),
  _priorCount: 0,

  getAllAssistantElements: function () {
    const selectors = [
      "[data-message-author-role='assistant']",
      "[data-testid*='assistant']",
      "article:has(.markdown)",
      "div.markdown",
      ".markdown",
      "[class*='markdown']",
      "div[data-testid^='conversation-turn-']:not([data-testid*='user'])",
      ".agent-turn",
      "div:has(button[aria-label*='Copy'], button[aria-label*='複製'], [data-testid*='copy'])"
    ];

    for (const sel of selectors) {
      try {
        const list = Array.from(document.querySelectorAll(sel));
        const filtered = list.filter((el) => {
          if (!el) return false;
          // Filter out hidden elements
          if (el.offsetParent === null && el.offsetHeight === 0) return false;
          // Filter out user message elements
          if (el.getAttribute("data-message-author-role") === "user") return false;
          if (el.closest && el.closest("[data-message-author-role='user']")) return false;
          if (el.closest && el.closest("[data-testid*='user']")) return false;
          return true;
        });

        if (filtered.length > 0) {
          return filtered;
        }
      } catch (_) {}
    }

    // Ultimate fallback: all divs with class containing prose or markdown
    const prose = Array.from(document.querySelectorAll("div.prose, [class*='prose']")).filter(
      (el) => !el.closest("[data-message-author-role='user']")
    );
    return prose;
  },

  snapshotBeforeTurn: function (turnId) {
    const all = this.getAllAssistantElements();
    this._priorElements = new Set(all);
    this._priorCount = all.length;

    all.forEach((el) => {
      try {
        el.setAttribute("data-w2l-turn", "prior");
      } catch (_) {}
    });
    console.log(`[ChatGpt Bridge] Snapshot before turn ${turnId}: ${this._priorCount} prior assistant elements.`);
    return this._priorCount;
  },

  findCurrentTurnResponseElement: function () {
    const all = this.getAllAssistantElements();
    if (all.length === 0) return null;

    // 1. Check from end for an element not in prior set and not tagged prior
    for (let i = all.length - 1; i >= 0; i--) {
      const el = all[i];
      if (!this._priorElements.has(el) && el.getAttribute("data-w2l-turn") !== "prior") {
        return el;
      }
    }

    // 2. If new elements appeared after the snapshot
    if (all.length > this._priorCount) {
      return all[all.length - 1];
    }

    // 3. If prior count was 0 (fresh chat), the newest assistant element is the target
    if (this._priorCount === 0 && all.length > 0) {
      return all[all.length - 1];
    }

    return null;
  },

  detectErrorBanner: function () {
    const errorSelectors = [
      "div[role='alert']",
      ".text-red-500",
      "div.border-red-500",
      "[data-testid*='error']",
      ".toast-error"
    ];

    for (const sel of errorSelectors) {
      const els = document.querySelectorAll(sel);
      for (const el of els) {
        if (el && el.offsetParent !== null) {
          const text = (el.innerText || el.textContent || "").trim();
          if (/too many requests|rate limit|verify you are human|cloudflare|something went wrong|unable to load|伺服器忙碌|請稍後再試/i.test(text)) {
            return text;
          }
        }
      }
    }

    if (document.title.includes("Just a moment...") || document.querySelector("#challenge-running, #challenge-form")) {
      return "ChatGPT 遭遇 Cloudflare 人機驗證挑戰，請在瀏覽器分頁中手動完成驗證。";
    }

    return null;
  },

  extractCurrentState: function (targetEl) {
    if (!targetEl) {
      targetEl = this.findCurrentTurnResponseElement();
    }
    if (!targetEl) {
      return { text: "", thought: "" };
    }

    // 1. Thinking / reasoning block (o1/o3/thinking models)
    let thoughtText = "";
    try {
      const thoughtEl = targetEl.querySelector(
        "div[data-testid='thought-container'], .thought-content, div.thought, [data-thought], button:has([data-testid*='thought'])"
      );
      if (thoughtEl) {
        thoughtText = (thoughtEl.innerText || "").trim();
      }
    } catch (_) {}

    // 2. Locate main markdown content container
    let contentEl = targetEl.querySelector(".markdown") || targetEl.querySelector("[class*='markdown']") || targetEl;
    let mainMarkdown = "";

    if (window.GeminiMarkdownSerializer) {
      try {
        mainMarkdown = window.GeminiMarkdownSerializer.serialize(contentEl);
      } catch (_) {}
    }

    // Bulletproof Fallback: if serializer returns empty, extract innerText directly
    if (!mainMarkdown || mainMarkdown.trim().length === 0) {
      mainMarkdown = (contentEl.innerText || contentEl.textContent || "").trim();
    }

    // Strip thought text if included inside contentEl
    if (thoughtText && mainMarkdown.includes(thoughtText)) {
      mainMarkdown = mainMarkdown.replace(thoughtText, "").trim();
    }

    // Clean up trailing button artifacts (e.g. Copy, Share, 複製)
    mainMarkdown = mainMarkdown.replace(/\n*(?:Copy|Share|複製|分享|重新產生|Regenerate)\s*$/gi, "").trim();

    return {
      text: mainMarkdown,
      thought: thoughtText,
    };
  },
};

if (typeof window !== "undefined") {
  window.ChatGptExtractor = ChatGptExtractor;
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = ChatGptExtractor;
}
