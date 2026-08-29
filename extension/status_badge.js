/**
 * WebChat2Local UI Status Badge (OpenDesign Minimalist Style with Manual Disconnect Support)
 */

(function () {
  function createBadge() {
    if (document.getElementById("webchat2local-badge")) return;

    const badge = document.createElement("div");
    badge.id = "webchat2local-badge";
    badge.className = "w2l-badge w2l-disconnected";
    badge.innerHTML = `
      <div class="w2l-dot"></div>
      <div class="w2l-content">
        <span class="w2l-title">WebChat2Local</span>
        <span class="w2l-status">連線中...</span>
        <button type="button" class="w2l-btn-mini" id="w2l-bar-disconnect-btn" style="display:none; background:#ef4444; color:#fff; border:none; border-radius:3px; padding:2px 6px; cursor:pointer; font-size:10px; margin-left:4px;">中斷</button>
        <button type="button" class="w2l-btn-mini" id="w2l-bar-connect-btn" style="display:none; background:#10b981; color:#fff; border:none; border-radius:3px; padding:2px 6px; cursor:pointer; font-size:10px; margin-left:4px;">連線</button>
      </div>
      <div class="w2l-details" id="w2l-details">
        <div class="w2l-details-header">本地 API 橋接狀態</div>
        <div class="w2l-row"><span>Base URL:</span> <code>http://127.0.0.1:8765/v1</code></div>
        <div class="w2l-row"><span>連線狀態:</span> <strong id="w2l-state-text">未連線</strong></div>
        <div class="w2l-row"><span>帳號:</span> <span id="w2l-user-text">-</span></div>
        <div class="w2l-row"><span>作用中請求:</span> <span id="w2l-active-req">0</span></div>
        <div class="w2l-actions">
          <button type="button" class="w2l-btn" id="w2l-card-disconnect-btn" style="background:#ef4444; color:#fff; border:none; display:none;">中斷本頁連線</button>
          <button type="button" class="w2l-btn" id="w2l-card-connect-btn" style="background:#10b981; color:#fff; border:none; display:none;">恢復連線</button>
          <a href="http://127.0.0.1:8765" target="_blank" class="w2l-btn">開啟控制面板</a>
        </div>
      </div>
    `;

    document.body.appendChild(badge);

    function triggerDisconnect(e) {
      if (e) { e.preventDefault(); e.stopPropagation(); }
      if (window.WebChat2LocalBridge && typeof window.WebChat2LocalBridge.disconnect === "function") {
        window.WebChat2LocalBridge.disconnect();
      }
    }

    function triggerConnect(e) {
      if (e) { e.preventDefault(); e.stopPropagation(); }
      if (window.WebChat2LocalBridge && typeof window.WebChat2LocalBridge.connect === "function") {
        window.WebChat2LocalBridge.connect();
      }
    }

    const barDisBtn = badge.querySelector("#w2l-bar-disconnect-btn");
    const barConnBtn = badge.querySelector("#w2l-bar-connect-btn");
    const cardDisBtn = badge.querySelector("#w2l-card-disconnect-btn");
    const cardConnBtn = badge.querySelector("#w2l-card-connect-btn");

    if (barDisBtn) barDisBtn.addEventListener("click", triggerDisconnect);
    if (barConnBtn) barConnBtn.addEventListener("click", triggerConnect);
    if (cardDisBtn) cardDisBtn.addEventListener("click", triggerDisconnect);
    if (cardConnBtn) cardConnBtn.addEventListener("click", triggerConnect);

    badge.addEventListener("click", (e) => {
      if (e.target.tagName.toLowerCase() === "a" || e.target.tagName.toLowerCase() === "button" || e.target.closest("button")) return;
      badge.classList.toggle("w2l-expanded");
    });

    if (window.WebChat2LocalBridge) {
      window.WebChat2LocalBridge.listeners.push(updateBadgeState);
      updateBadgeState(window.WebChat2LocalBridge);
    }
  }

  function updateBadgeState(bridge) {
    const badge = document.getElementById("webchat2local-badge");
    if (!badge) return;

    const statusText = badge.querySelector(".w2l-status");
    const stateText = document.getElementById("w2l-state-text");
    const userText = document.getElementById("w2l-user-text");
    const activeReq = document.getElementById("w2l-active-req");

    const barDisBtn = badge.querySelector("#w2l-bar-disconnect-btn");
    const barConnBtn = badge.querySelector("#w2l-bar-connect-btn");
    const cardDisBtn = badge.querySelector("#w2l-card-disconnect-btn");
    const cardConnBtn = badge.querySelector("#w2l-card-connect-btn");

    badge.classList.remove("w2l-connected", "w2l-disconnected", "w2l-connecting", "w2l-busy");

    if (bridge.status === "connected") {
      if (barDisBtn) barDisBtn.style.display = "inline-flex";
      if (barConnBtn) barConnBtn.style.display = "none";
      if (cardDisBtn) cardDisBtn.style.display = "inline-block";
      if (cardConnBtn) cardConnBtn.style.display = "none";

      if (bridge.activeRequests > 0) {
        badge.classList.add("w2l-busy");
        statusText.textContent = `處理中 (${bridge.activeRequests})`;
        stateText.textContent = "傳輸中";
        stateText.style.color = "#3b82f6";
      } else {
        badge.classList.add("w2l-connected");
        statusText.textContent = "已連線";
        stateText.textContent = "已連線";
        stateText.style.color = "#10b981";
      }
    } else if (bridge.status === "connecting") {
      if (barDisBtn) barDisBtn.style.display = "none";
      if (barConnBtn) barConnBtn.style.display = "none";
      if (cardDisBtn) cardDisBtn.style.display = "none";
      if (cardConnBtn) cardConnBtn.style.display = "none";

      badge.classList.add("w2l-connecting");
      const attemptInfo = bridge.retryCount ? ` (${bridge.retryCount}/${bridge.maxRetries || 3})` : "";
      statusText.textContent = `連線中${attemptInfo}...`;
      stateText.textContent = `正在尋找本地伺服器${attemptInfo}...`;
      stateText.style.color = "#f59e0b";
    } else {
      badge.classList.add("w2l-disconnected");
      statusText.textContent = bridge.manualDisconnected ? "已自主中斷" : "未連線";
      
      if (barDisBtn) barDisBtn.style.display = "none";
      if (barConnBtn) barConnBtn.style.display = "inline-flex";
      if (cardDisBtn) cardDisBtn.style.display = "none";
      if (cardConnBtn) cardConnBtn.style.display = "inline-block";

      if (bridge.manualDisconnected) {
        stateText.textContent = "已自主中斷連線 (點擊按鈕可恢復)";
      } else if (bridge.retryExhausted) {
        stateText.textContent = `未連線 (已嘗試 ${bridge.maxRetries || 3} 次，請確認伺服器已啟動)`;
      } else {
        stateText.textContent = "未連線 (等待伺服器)";
      }
      stateText.style.color = "#ef4444";
    }

    if (userText && bridge.userInfo) {
      userText.textContent = bridge.userInfo.email || bridge.userInfo.name || "已認證";
    }
    if (activeReq) {
      activeReq.textContent = bridge.activeRequests || "0";
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", createBadge);
  } else {
    createBadge();
  }
})();
