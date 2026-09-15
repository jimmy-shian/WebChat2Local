/**
 * Gemini 對話批次刪除器 (Gemini-only)
 *
 * 在 gemini.google.com 頁面注入操作 HUD，一鍵批次刪除歷史對話。
 * 觸發方式：
 *   1. 擴充套件 popup「批次刪除 Gemini 對話」按鈕
 *      -> chrome.tabs.sendMessage({ type: "w2l-cleaner-start" })
 *   2. Console 手動呼叫 window.GeminiCleaner.start({ total: 120 })
 *
 * 遵循 repo 慣例：瀏覽器掛 window.GeminiCleaner，Node 下 module.exports 以便測試。
 */

const GeminiCleaner = (() => {
  const MSG_START = "w2l-cleaner-start";
  const DEFAULT_TOTAL = 120;
  const DEFAULT_DELAY_MS = 1000;
  const MAX_MISS = 3; // 連續找不到按鈕幾次後判定為已刪完並結束（避免列表載入中誤判）

  const SELECTORS = {
    moreButton: 'button[aria-label$="的更多動作選項"], [data-test-id="actions-menu-button"] button',
    deleteMenuButton: 'button[data-test-id="delete-button"]',
    dialog: '[role="dialog"]',
  };

  const state = {
    running: false,
    paused: false,
    stoppedByUser: false,
    count: 0,
    total: DEFAULT_TOTAL,
    infinite: false,
    delayMs: DEFAULT_DELAY_MS,
    misses: 0,
    runToken: 0,
    hud: null,
    refs: null,
    styleEl: null,
  };

  function isSupportedPage() {
    try {
      return (
        typeof window !== "undefined" &&
        !!window.location &&
        window.location.hostname.includes("gemini.google.com")
      );
    } catch (_) {
      return false;
    }
  }

  function canRunDom() {
    return typeof document !== "undefined" && isSupportedPage();
  }

  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function waitForElement(selector, timeout = 4000) {
    return new Promise((resolve, reject) => {
      const el = document.querySelector(selector);
      if (el) return resolve(el);

      const observer = new MutationObserver(() => {
        const target = document.querySelector(selector);
        if (target) {
          observer.disconnect();
          resolve(target);
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });

      setTimeout(() => {
        observer.disconnect();
        reject(new Error(`等待元素逾時: ${selector}`));
      }, timeout);
    });
  }

  // 模擬真人的完整滑鼠點擊事件（相容 Angular Material Trigger）
  function triggerRealClick(el) {
    const rect = el.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const opts = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y };

    el.dispatchEvent(new MouseEvent("mousedown", opts));
    el.dispatchEvent(new MouseEvent("mouseup", opts));
    el.dispatchEvent(new MouseEvent("click", opts));
  }

  function parseTotalInput(value, fallback) {
    const n = parseInt(value, 10);
    if (Number.isFinite(n) && n > 0) return Math.min(n, 100000);
    return fallback;
  }

  function parseDelayInput(value, fallback) {
    const n = parseInt(value, 10);
    if (!Number.isFinite(n)) return fallback;
    return Math.min(Math.max(n, 200), 5000); // 下限 200ms：太短會點到舊列表元素
  }

  function ensureStyle() {
    if (state.styleEl || typeof document === "undefined") return;
    const styleEl = document.createElement("style");
    styleEl.id = "gemini-unlock-action-menu";
    styleEl.textContent = `
      .hovered-trailing-content,
      [data-test-id="actions-menu-button"],
      .gem-conversation-actions-menu-button {
        opacity: 1 !important;
        visibility: visible !important;
        display: inline-flex !important;
        width: auto !important;
        height: auto !important;
        pointer-events: auto !important;
      }
    `;
    document.head.appendChild(styleEl);
    state.styleEl = styleEl;
  }

  function removeStyle() {
    if (state.styleEl) {
      try { state.styleEl.remove(); } catch (_) {}
      state.styleEl = null;
    }
  }

  function progressText() {
    return state.infinite ? `${state.count} / ∞` : `${state.count} / ${state.total}`;
  }

  function render() {
    const refs = state.refs;
    if (!refs) return;
    refs.count.textContent = progressText();
    refs.totalInput.disabled = state.infinite || state.running;
    refs.infiniteBox.disabled = state.running;
    refs.delayInput.disabled = state.running;
    refs.startBtn.textContent = state.count > 0 || state.running ? "重新開始" : "開始";
    refs.pauseBtn.textContent = state.paused ? "繼續" : "暫停";
    refs.pauseBtn.style.background = state.paused ? "#81c784" : "#ffa726";
  }

  function setStatus(text, color) {
    if (state.refs) {
      state.refs.status.textContent = text;
      state.refs.status.style.color = color || "#64b5f6";
    }
  }

  function buildHud() {
    if (state.hud) return;
    ensureStyle();

    const hud = document.createElement("div");
    hud.id = "w2l-gemini-cleaner-hud";
    hud.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 2147483647;
      background: rgba(18, 18, 18, 0.95);
      color: #fff;
      padding: 16px 20px;
      border-radius: 10px;
      font-size: 14px;
      font-family: system-ui, sans-serif;
      box-shadow: 0 4px 20px rgba(0,0,0,0.5);
      border: 1px solid rgba(255, 255, 255, 0.15);
      min-width: 240px;
      pointer-events: auto;
    `;

    hud.innerHTML = `
      <div style="font-weight: bold; margin-bottom: 8px;">🗑️ Gemini 對話批次刪除</div>
      <div id="w2l-cleaner-status" style="color: #64b5f6; margin-bottom: 6px;">狀態：待命</div>
      <div style="margin-bottom: 8px;">進度：<b id="w2l-cleaner-count" style="color: #81c784; font-size: 16px;">0 / ${state.total}</b></div>
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap;">
        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px;">
          次數 <input id="w2l-cleaner-total" type="number" min="1" max="100000" value="${state.total}"
            style="width: 76px; padding: 4px 6px; border-radius: 6px; border: 1px solid #555; background: #222; color: #fff;">
        </label>
        <label style="display: flex; align-items: center; gap: 4px; font-size: 13px; cursor: pointer;">
          <input id="w2l-cleaner-infinite" type="checkbox" style="accent-color: #81c784;"> 無限
        </label>
        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px;">
          間隔 <input id="w2l-cleaner-delay" type="number" min="200" max="5000" step="100" value="${state.delayMs}"
            style="width: 70px; padding: 4px 6px; border-radius: 6px; border: 1px solid #555; background: #222; color: #fff;"> ms
        </label>
      </div>
      <div style="display: flex; gap: 8px; margin-bottom: 8px;">
        <button id="w2l-cleaner-start" style="flex: 1; padding: 6px; border-radius: 6px; border: none; background: #81c784; color: #111; font-weight: bold; cursor: pointer;">開始</button>
        <button id="w2l-cleaner-pause" style="flex: 1; padding: 6px; border-radius: 6px; border: none; background: #ffa726; color: #111; font-weight: bold; cursor: pointer;">暫停</button>
      </div>
      <div style="display: flex; gap: 8px;">
        <button id="w2l-cleaner-stop" style="flex: 1; padding: 6px; border-radius: 6px; border: none; background: #e57373; color: #fff; font-weight: bold; cursor: pointer;">終止</button>
        <button id="w2l-cleaner-close" style="flex: 1; padding: 6px; border-radius: 6px; border: 1px solid #777; background: transparent; color: #ccc; cursor: pointer;">關閉</button>
      </div>
    `;
    document.body.appendChild(hud);

    state.hud = hud;
    state.refs = {
      status: hud.querySelector("#w2l-cleaner-status"),
      count: hud.querySelector("#w2l-cleaner-count"),
      totalInput: hud.querySelector("#w2l-cleaner-total"),
      infiniteBox: hud.querySelector("#w2l-cleaner-infinite"),
      delayInput: hud.querySelector("#w2l-cleaner-delay"),
      startBtn: hud.querySelector("#w2l-cleaner-start"),
      pauseBtn: hud.querySelector("#w2l-cleaner-pause"),
      stopBtn: hud.querySelector("#w2l-cleaner-stop"),
      closeBtn: hud.querySelector("#w2l-cleaner-close"),
    };

    state.refs.startBtn.addEventListener("click", () => {
      start({
        total: parseTotalInput(state.refs.totalInput.value, state.total),
        infinite: state.refs.infiniteBox.checked,
        delayMs: parseDelayInput(state.refs.delayInput.value, state.delayMs),
      });
    });
    state.refs.pauseBtn.addEventListener("click", pauseToggle);
    state.refs.stopBtn.addEventListener("click", stop);
    state.refs.closeBtn.addEventListener("click", close);
    setStatus("狀態：待命（設定次數後按開始）", "#64b5f6");
    render();
  }

  async function runLoop(token) {
    const isActive = () => token === state.runToken && state.running;
    setStatus("狀態：🚀 執行中...");

    while (isActive()) {
      while (state.paused && isActive()) {
        await wait(200);
      }
      if (!isActive()) break;
      if (!state.infinite && state.count >= state.total) break;

      try {
        const firstMoreButton = document.querySelector(SELECTORS.moreButton);

        if (!firstMoreButton) {
          state.misses++;
          if (state.misses >= MAX_MISS) {
            setStatus("狀態：找不到對話按鈕，可能已全數刪除，結束。", "#81c784");
            break;
          }
          setStatus(`狀態：等待列表載入…（${state.misses}/${MAX_MISS}）`, "#ffa726");
          await wait(1500);
          continue;
        }
        state.misses = 0;

        // 觸發所屬列的 hover 以防 Angular 事件未被啟動
        const rowItem =
          (firstMoreButton.closest(".hovered-trailing-content") || {}).parentElement ||
          firstMoreButton;
        rowItem.dispatchEvent(new MouseEvent("mouseenter", { bubbles: true }));
        rowItem.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
        await wait(100);
        if (!isActive()) break;

        triggerRealClick(firstMoreButton);

        const deleteMenuButton = await waitForElement(SELECTORS.deleteMenuButton, 3000);
        await wait(120);
        deleteMenuButton.click();

        await waitForElement(SELECTORS.dialog, 3000);
        await wait(120);

        const dialog = document.querySelector(SELECTORS.dialog);
        const confirmDeleteButton = [...dialog.querySelectorAll("button")].find(
          (btn) => (btn.innerText || "").trim() === "刪除"
        );
        if (!confirmDeleteButton) {
          throw new Error("找不到彈窗確認刪除按鈕");
        }
        confirmDeleteButton.click();

        state.count++;
        render();
        console.log(`[GeminiCleaner ${state.count}${state.infinite ? "" : "/" + state.total}] ✅ 已刪除一筆對話`);

        // 等待 Google 後端資料庫與列表完成重新渲染
        await wait(state.delayMs);
      } catch (err) {
        console.warn("[GeminiCleaner] 刪除步驟遇到問題，關閉覆蓋層並重試：", err);
        try { document.body.click(); } catch (_) {}
        setStatus("狀態：遇到阻擋，已關閉覆蓋層重試…", "#ffa726");
        await wait(1000);
      }
    }

    if (token !== state.runToken) return; // 已被新一輪取代
    state.running = false;
    state.paused = false;
    if (!state.infinite && state.count >= state.total) {
      setStatus("狀態：🎉 已全數清理完成！", "#81c784");
    } else if (state.stoppedByUser) {
      setStatus("狀態：🛑 已中途終止", "#e57373");
    } else if (!state.refs) {
      // HUD 已關閉，無需更新
    } else {
      setStatus("狀態：待命", "#64b5f6");
    }
    render();
  }

  /**
   * 僅開啟 HUD 並停在待命（不開跑），讓使用者先設定次數/無限再按開始。
   * @returns {boolean} 是否成功開啟（非 Gemini 分頁回傳 false）
   */
  function open() {
    if (!canRunDom()) return false;
    const wasRunning = state.running;
    buildHud();
    if (!wasRunning && !state.running) {
      setStatus("狀態：待命（設定次數後按開始）", "#64b5f6");
      render();
    }
    return true;
  }

  /**
   * 開啟 HUD 並開始（或重新開始）批次刪除。
   * @param {object} opts { total?: number, infinite?: boolean, delayMs?: number }
   * @returns {boolean} 是否成功啟動（非 Gemini 分頁回傳 false）
   */
  function start(opts) {
    if (!canRunDom()) return false;
    const o = opts || {};
    if (Number.isFinite(o.total) && o.total > 0) state.total = Math.min(Math.floor(o.total), 100000);
    if (typeof o.infinite === "boolean") state.infinite = o.infinite;
    if (Number.isFinite(o.delayMs) && o.delayMs >= 0) state.delayMs = o.delayMs;

    buildHud();
    // HUD 輸入框優先（使用者可能直接在 UI 上改了次數/無限/間隔）
    if (state.refs) {
      state.total = parseTotalInput(state.refs.totalInput.value, state.total);
      state.infinite = state.refs.infiniteBox.checked || state.infinite;
      state.delayMs = parseDelayInput(state.refs.delayInput.value, state.delayMs);
      if (typeof o.infinite === "boolean") state.refs.infiniteBox.checked = state.infinite;
      state.refs.totalInput.value = state.total;
      state.refs.delayInput.value = state.delayMs;
    }

    state.count = 0;
    state.misses = 0;
    state.paused = false;
    state.stoppedByUser = false;
    state.running = true;
    state.runToken++;
    render();
    runLoop(state.runToken);
    return true;
  }

  function pauseToggle() {
    if (!state.running) return state.paused;
    state.paused = !state.paused;
    setStatus(
      state.paused ? "狀態：⏸️ 已暫停" : "狀態：🚀 執行中...",
      state.paused ? "#ffa726" : "#64b5f6"
    );
    render();
    return state.paused;
  }

  function stop() {
    state.stoppedByUser = true;
    state.paused = false;
    state.running = false;
    state.runToken++; // 作廢進行中的迴圈
    setStatus("狀態：🛑 已中途終止", "#e57373");
    render();
  }

  function close() {
    stop();
    if (state.hud) {
      try { state.hud.remove(); } catch (_) {}
      state.hud = null;
      state.refs = null;
    }
    removeStyle();
  }

  function getState() {
    return {
      running: state.running,
      paused: state.paused,
      count: state.count,
      total: state.total,
      infinite: state.infinite,
      delayMs: state.delayMs,
    };
  }

  // popup 按鈕經 tabs.sendMessage 觸發（僅 Gemini 分頁會載入本檔案）。
  // 預設只開面板不開跑（autostart:true 才直接開始），讓使用者先設定次數/無限。
  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
      if (msg && msg.type === MSG_START) {
        const ok = msg.autostart ? start((msg && msg.opts) || {}) : open();
        try { sendResponse({ ok, supported: isSupportedPage() }); } catch (_) {}
      }
      return false;
    });
  }

  return {
    open,
    start,
    stop,
    pauseToggle,
    close,
    isSupportedPage,
    getState,
    parseTotalInput,
    parseDelayInput,
    MSG_START,
    SELECTORS,
    DEFAULT_TOTAL,
    DEFAULT_DELAY_MS,
  };
})();

if (typeof window !== "undefined") {
  window.GeminiCleaner = GeminiCleaner;
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = GeminiCleaner;
}
