/**
 * Gemini Web Response Extractor
 * Extracts real-time streamed responses and thinking blocks from gemini.google.com DOM
 * with strict element-set isolation to prevent capturing prior messages.
 */

const GeminiExtractor = {
  _priorElements: new Set(),
  _priorCount: 0,

  // Tags and indexes all existing response elements before submitting a new prompt
  snapshotBeforeTurn: function (turnId) {
    const selector = "model-response, message-content, div.model-response-text, div.response-container-content, [data-test-id='model-response']";
    const all = Array.from(document.querySelectorAll(selector));
    this._priorElements = new Set(all);
    this._priorCount = all.length;

    all.forEach((el) => {
      el.setAttribute("data-w2l-turn", "prior");
    });
    console.log(`[Gemini Bridge] Snapshot taken before turn ${turnId}: ${this._priorCount} prior response elements.`);
    return this._priorCount;
  },

  // Finds the newly spawned response element for the current turn
  findCurrentTurnResponseElement: function () {
    const selector = "model-response, message-content, div.model-response-text, div.response-container-content, [data-test-id='model-response']";
    const current = Array.from(document.querySelectorAll(selector));

    // 1. Check from end for an element not in prior set
    for (let i = current.length - 1; i >= 0; i--) {
      const el = current[i];
      if (!this._priorElements.has(el) && el.getAttribute("data-w2l-turn") !== "prior") {
        return el;
      }
    }

    // 2. If new elements were added after the snapshot
    if (current.length > this._priorCount && current.length > 0) {
      const newest = current[current.length - 1];
      if (!this._priorElements.has(newest)) {
        return newest;
      }
    }

    // Strict rule: NEVER return an element from the prior snapshot
    return null;
  },

  extractCurrentState: function (targetEl) {
    if (!targetEl) {
      targetEl = this.findCurrentTurnResponseElement();
    }
    // If no new target element exists yet, return empty (DO NOT fallback to prior message!)
    if (!targetEl) {
      return { text: "", thought: "" };
    }

    // The caller already isolated the newly-created response element. From
    // here on, read that response box directly; do not score/filter arbitrary
    // strings from the page or network transport.
    // 1. Check for thinking / reasoning process container
    let thoughtText = "";
    const thoughtEl = targetEl.querySelector(
      "div.thought-container, expandable-thought, div.thinking-content, .thought-content, [data-thought], .thinking-process, div[class*='thought']"
    );
    if (thoughtEl) {
      thoughtText = (thoughtEl.innerText || "").trim();
    }

    // 2. Extract main markdown content
    let contentEl = targetEl.querySelector(".markdown") || targetEl;
    let mainMarkdown = "";
    if (window.GeminiMarkdownSerializer) {
      mainMarkdown = window.GeminiMarkdownSerializer.serialize(contentEl);
    } else {
      mainMarkdown = (contentEl.innerText || "").trim();
    }

    // If the thought container was included inside contentEl, remove it from mainMarkdown
    if (thoughtText && mainMarkdown.includes(thoughtText)) {
      mainMarkdown = mainMarkdown.replace(thoughtText, "").trim();
    }

    return {
      text: mainMarkdown,
      thought: thoughtText,
    };
  },
};

if (typeof window !== "undefined") {
  window.GeminiExtractor = GeminiExtractor;
}
