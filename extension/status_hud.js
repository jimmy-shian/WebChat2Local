/**
 * Gemini Web Floating Status HUD
 */

const GeminiStatusHUD = {
  rootEl: null,
  dotEl: null,
  textEl: null,

  init: function () {
    if (document.getElementById("w2l-hud-root")) return;

    const root = document.createElement("div");
    root.id = "w2l-hud-root";
    root.innerHTML = `
      <div class="w2l-hud-pill" title="Gemini Web to Local Bridge Status (點擊開啟儀表板)">
        <div class="w2l-hud-dot disconnected"></div>
        <span class="w2l-hud-text">Gemini Bridge 正在連線...</span>
        <button id="w2l-btn-new-chat" style="margin-left:8px;background:#2563eb;color:#fff;border:none;border-radius:4px;padding:2px 7px;cursor:pointer;font-size:11px;font-weight:bold;" title="手動重設/開啟新對話">➕ 新對話</button>
      </div>
    `;

    document.body.appendChild(root);
    this.rootEl = root;
    this.dotEl = root.querySelector(".w2l-hud-dot");
    this.textEl = root.querySelector(".w2l-hud-text");

    const newChatBtn = root.querySelector("#w2l-btn-new-chat");
    if (newChatBtn) {
      newChatBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (window.GeminiController && window.GeminiController.startNewChatIfAvailable) {
          window.GeminiController.startNewChatIfAvailable();
          this.setStatus("connected", "已手動開啟新對話");
        }
      });
    }

    root.addEventListener("click", () => {
      window.open("http://127.0.0.1:8765", "_blank");
    });
  },

  setStatus: function (state, message) {
    if (!this.dotEl) this.init();
    if (!this.dotEl) return;

    this.dotEl.className = `w2l-hud-dot ${state}`;
    this.textEl.textContent = message;
  },

  setConnected: function (detail) {
    this.setStatus("connected", detail || "Gemini Bridge 就緒 (會話常駐)");
  },

  setGenerating: function (turnId, model, sessionTag) {
    const modelTag = model ? ` (${model.replace("gemini-web/", "")})` : "";
    const tag = sessionTag ? ` · ${sessionTag}` : "";
    this.setStatus("generating", `⚡ 生成中${modelTag}${tag}...`);
  },

  setDisconnected: function () {
    this.setStatus("disconnected", "伺服器未連線 (8765)");
  },
};

if (typeof window !== "undefined") {
  window.GeminiStatusHUD = GeminiStatusHUD;
}
