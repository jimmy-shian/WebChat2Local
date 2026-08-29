/**
 * WebChat2Local UI Status Badge (OpenDesign Minimalist Style)
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
        <button type="button" class="w2l-btn-mini w2l-retry-btn" id="w2l-bar-retry-btn" style="display:none;">重試</button>
      </div>
      <div class="w2l-details" id="w2l-details">
        <div class="w2l-details-header">本地 API 橋接狀態</div>
        <div class="w2l-row"><span>Base URL:</span> <code>http://127.0.0.1:8765/v1</code></div>
        <div class="w2l-row"><span>連線狀態:</span> <strong id="w2l-state-text">未連線</strong></div>
        <div class="w2l-row"><span>帳號:</span> <span id="w2l-user-text">-</span></div>
        <div class="w2l-row"><span>作用中請求:</span> <span id="w2l-active-req">0</span></div>
        <div class="w2l-actions">
          <button type="button" class="w2l-btn w2l-retry-btn" id="w2l-card-retry-btn" style="display:none;">重試連線</button>
          <a href="http://127.0.0.1:8765" target="_blank" class="w2l-btn">開啟控制面板</a>
        </div>
      </div>
    `;

    document.body.appendChild(badge);

    function triggerRetry(e) {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      if (window.WebChat2LocalBridge && typeof window.WebChat2LocalBridge.retry === "function") {
        window.WebChat2LocalBridge.retry();
      }
    }

    const barRetryBtn = badge.querySelector("#w2l-bar-retry-btn");
    const cardRetryBtn = badge.querySelector("#w2l-card-retry-btn");

    if (barRetryBtn) {
      barRetryBtn.addEventListener("click", triggerRetry);
    }
    if (cardRetryBtn) {
      cardRetryBtn.addEventListener("click", triggerRetry);
    }

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
    const barRetryBtn = badge.querySelector("#w2l-bar-retry-btn");
    const cardRetryBtn = badge.querySelector("#w2l-card-retry-btn");

    badge.classList.remove("w2l-connected", "w2l-disconnected", "w2l-connecting", "w2l-busy");

    if (bridge.status === "connected") {
      if (barRetryBtn) barRetryBtn.style.display = "none";
      if (cardRetryBtn) cardRetryBtn.style.display = "none";

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
      if (barRetryBtn) barRetryBtn.style.display = "none";
      if (cardRetryBtn) cardRetryBtn.style.display = "none";

      badge.classList.add("w2l-connecting");
      const attemptInfo = bridge.retryCount ? ` (${bridge.retryCount}/${bridge.maxRetries || 3})` : "";
      statusText.textContent = `連線中${attemptInfo}...`;
      stateText.textContent = `正在尋找本地伺服器${attemptInfo}...`;
      stateText.style.color = "#f59e0b";
    } else {
      badge.classList.add("w2l-disconnected");
      statusText.textContent = "未連線";
      
      if (barRetryBtn) barRetryBtn.style.display = "inline-flex";
      if (cardRetryBtn) cardRetryBtn.style.display = "inline-block";

      if (bridge.retryExhausted) {
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
