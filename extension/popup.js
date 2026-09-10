document.addEventListener("DOMContentLoaded", () => {
  const btnCapture = document.getElementById("btn-capture");
  const btnCopyConfig = document.getElementById("btn-copy-config");
  const tabStatus = document.getElementById("tab-status");
  const msg = document.getElementById("msg");

  const tabDot = document.getElementById("tab-dot");
  const chkClean = document.getElementById("setting-clean-session");
  const chkAutoDismiss = document.getElementById("setting-auto-dismiss");

  const seg = document.getElementById("transport-seg");
  const transportHint = document.getElementById("transport-hint");

  // 右上小視窗顯示版本號（單一來源：manifest.json）
  try {
    const ver = chrome.runtime.getManifest().version;
    const el = document.getElementById("ext-version");
    if (el && ver) el.textContent = "v" + ver;
  } catch (_) {}

  const setTabStatus = (ok, html) => {
    if (tabDot) tabDot.className = "dot" + (ok === true ? " ok" : ok === false ? " bad" : "");
    if (tabStatus) tabStatus.innerHTML = html;
  };

  const MODE_HINT = {
    auto: "自動：Cookie 直連優先，失敗時 fallback 到瀏覽器分頁。",
    direct: "直連：只用 Cookie 打 gemini.google.com，不需開分頁。ChatGPT 模型不適用。",
    extension: "Web 視窗：強制走瀏覽器分頁（需開 gemini / chatgpt 分頁）。",
  };

  const paintTransport = (mode, extra) => {
    if (seg) {
      seg.querySelectorAll("button").forEach((b) => {
        b.classList.toggle("active", b.dataset.mode === mode);
      });
    }
    if (transportHint) {
      transportHint.textContent = (MODE_HINT[mode] || mode) + (extra ? " " + extra : "");
    }
  };

  const fetchTransport = async () => {
    paintTransport("auto", "");
    if (transportHint) transportHint.textContent = "讀取中…";
    try {
      const controller = new AbortController();
      const t = setTimeout(() => controller.abort(), 2500);
      const r = await fetch("http://127.0.0.1:8765/v1/transport", {
        cache: "no-store",
        signal: controller.signal,
      });
      clearTimeout(t);
      if (!r.ok) throw new Error("bad status");
      const d = await r.json();
      const mode = d.mode || "auto";
      let extra = "";
      if (mode === "direct" && !d.direct_configured) extra = "（尚未設定 Cookie，請先同步）";
      if (mode === "extension" && !d.browser_connected) extra = "（尚未偵測到分頁，請開啟 gemini / chatgpt）";
      paintTransport(mode, extra);
    } catch (_) {
      if (transportHint) transportHint.textContent = "伺服器未啟動，傳輸模式請到本地控制面板切換。";
    }
  };

  if (seg) {
    seg.querySelectorAll("button").forEach((b) => {
      b.addEventListener("click", async () => {
        const mode = b.dataset.mode;
        paintTransport(mode, "");
        try {
          const r = await fetch("http://127.0.0.1:8765/v1/transport", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode }),
          });
          if (!r.ok) {
            const e = await r.json().catch(() => ({}));
            throw new Error(e.detail || "切換失敗");
          }
          const d = await r.json();
          paintTransport(d.mode || mode, "");
          msg.textContent = "傳輸模式已切換：" + (d.mode || mode);
          msg.className = "msg ok";
        } catch (e) {
          if (transportHint) transportHint.textContent = "切換失敗（伺服器未啟動？）：" + (e.message || e);
        }
      });
    });
    fetchTransport();
  }

  // 1. Load preferences (相容舊版 autoReload / forceNewChat)
  chrome.storage.local.get({
    cleanSession: null,
    autoReload: true,
    forceNewChat: true,
    autoDismissModals: true
  }, (res) => {
    let clean = res.cleanSession;
    if (clean === null || clean === undefined) {
      // 舊資料：任一為 true 即視為乾淨會話開啟（兩者本來就是同一目的）
      clean = !!(res.autoReload || res.forceNewChat);
    }
    if (chkClean) chkClean.checked = !!clean;
    if (chkAutoDismiss) chkAutoDismiss.checked = !!res.autoDismissModals;
  });

  // 2. Save on toggle (單一開關同時寫入新舊 key，保持 content.js 相容)
  const saveSettings = () => {
    const clean = chkClean ? chkClean.checked : true;
    chrome.storage.local.set({
      cleanSession: clean,
      // 舊版 content.js 只讀這兩個 key：合併寫入同一個值即消除重複邏輯
      autoReload: clean,
      forceNewChat: clean,
      autoDismissModals: chkAutoDismiss ? chkAutoDismiss.checked : true
    }, () => {
      msg.textContent = "偏好設定已儲存";
      msg.className = "msg ok";
      setTimeout(() => { if (msg.textContent.includes("偏好設定")) msg.textContent = ""; }, 2000);
    });
  };

  if (chkClean) chkClean.addEventListener("change", saveSettings);
  if (chkAutoDismiss) chkAutoDismiss.addEventListener("change", saveSettings);

  // 3. Detect current tab
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs || tabs.length === 0) return;
    const url = tabs[0].url || "";
    if (url.includes("chatgpt.com")) {
      setTabStatus(true, "當前分頁：<strong>ChatGPT Web（免登入可用）</strong>");
    } else if (url.includes("gemini.google.com")) {
      setTabStatus(true, "當前分頁：<strong>Google Gemini Web</strong>");
    } else {
      setTabStatus(false, "非支援分頁，請開啟 <a href='https://chatgpt.com' target='_blank'>chatgpt.com</a> 或 <a href='https://gemini.google.com' target='_blank'>gemini.google.com</a>");
    }
  });

  if (btnCopyConfig) {
    btnCopyConfig.addEventListener("click", () => {
      const configJson = {
        apiProvider: "openai",
        openAiBaseUrl: "http://127.0.0.1:8765/v1",
        openAiApiKey: "sk-local",
        openAiModelId: "webchat/auto",
        customModelInfo: {
          supportsPromptCache: false,
          maxTokens: 4096,
          contextWindow: 32768,
          supportsThinking: true,
        },
      };
      navigator.clipboard.writeText(JSON.stringify(configJson, null, 2)).then(() => {
        msg.textContent = "已複製 IDE 配置（webchat/auto）";
        msg.className = "msg ok";
      }).catch(() => {
        msg.textContent = "複製失敗，請手動複製端點 127.0.0.1:8765/v1。";
        msg.className = "msg err";
      });
    });
  }

  if (btnCapture) {
    btnCapture.addEventListener("click", async () => {
      btnCapture.disabled = true;
      msg.textContent = "正在讀取 Gemini Cookie...";
      msg.className = "msg";
      try {
        const cookies = await fetchCurrentCookies();
        const jsonStr = JSON.stringify(cookies, null, 2);

        // Auto copy to clipboard (取代舊版「複製 Cookie JSON」按鈕)
        try { await navigator.clipboard.writeText(jsonStr); } catch (_) {}

        // Try syncing to local server
        msg.textContent = "正在同步至本地伺服器...";
        let syncedToServer = false;
        try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 2000);
          const resp = await fetch("http://127.0.0.1:8765/v1/cookies", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: jsonStr,
            signal: controller.signal,
          });
          clearTimeout(timeoutId);
          if (resp.ok) syncedToServer = true;
        } catch (_) {
          syncedToServer = false;
        }

        if (syncedToServer) {
          msg.innerHTML = "已同步至本地 <code>gemini_cookies.json</code>（已自動複製備用）";
          msg.className = "msg ok";
        } else {
          msg.textContent = "Cookie 已複製至剪貼簿（伺服器未啟動時，可手動貼入 gemini_cookies.json）";
          msg.className = "msg ok";
        }
      } catch (e) {
        msg.textContent = `${e.message || e}`;
        msg.className = "msg err";
      } finally {
        btnCapture.disabled = false;
      }
    });
  }
});

async function fetchCurrentCookies() {
  const onePsid = await getCookie("__Secure-1PSID");
  const onePsidts = await getCookie("__Secure-1PSIDTS");

  if (!onePsid) {
    throw new Error("找不到 __Secure-1PSID，若使用 Gemini 請先在瀏覽器分頁登入 https://gemini.google.com");
  }

  return {
    "1psid": onePsid,
    "1psidts": onePsidts || "",
  };
}

async function getCookie(name) {
  let val = await new Promise((resolve) => {
    chrome.cookies.get({ url: "https://gemini.google.com", name }, (cookie) => {
      resolve(cookie ? cookie.value : "");
    });
  });
  if (val) return val;

  val = await new Promise((resolve) => {
    chrome.cookies.get({ url: "https://google.com", name }, (cookie) => {
      resolve(cookie ? cookie.value : "");
    });
  });
  if (val) return val;

  val = await new Promise((resolve) => {
    chrome.cookies.getAll({ name }, (cookies) => {
      if (chrome.runtime.lastError || !cookies || cookies.length === 0) {
        return resolve("");
      }
      const match = cookies.find((c) => c.domain && c.domain.includes("google.com"));
      resolve(match ? match.value : cookies[0].value);
    });
  });
  return val || "";
}
