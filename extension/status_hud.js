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
      <div class="w2l-hud-pill" title="Gemini Web to Local Bridge Status (Click to open Dashboard)">
        <div class="w2l-hud-dot disconnected"></div>
        <span class="w2l-hud-text">Gemini Bridge 正在連線...</span>
      </div>
    `;

    document.body.appendChild(root);
    this.rootEl = root;
    this.dotEl = root.querySelector(".w2l-hud-dot");
    this.textEl = root.querySelector(".w2l-hud-text");

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

  setConnected: function () {
    this.setStatus("connected", "Gemini Bridge 就緒");
  },

  setGenerating: function (turnId, model) {
    const modelTag = model ? ` (${model.replace("gemini-web/", "")})` : "";
    this.setStatus("generating", `⚡ 生成中${modelTag}...`);
  },

  setDisconnected: function () {
    this.setStatus("disconnected", "伺服器未連線 (8765)");
  },
};

if (typeof window !== "undefined") {
  window.GeminiStatusHUD = GeminiStatusHUD;
}
