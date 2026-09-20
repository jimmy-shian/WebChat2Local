document.addEventListener("DOMContentLoaded", () => {
  const btnCapture = document.getElementById("btn-capture");
  const btnDeepseek = document.getElementById("btn-deepseek");
  const btnCleaner = document.getElementById("btn-cleaner");
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

  const epChip = document.getElementById("endpoint-chip");
  if (epChip) {
    epChip.addEventListener("click", () => {
      navigator.clipboard.writeText("http://127.0.0.1:8765/v1").then(() => {
        msg.textContent = "已複製端點 127.0.0.1:8765/v1";
        msg.className = "msg ok";
        setTimeout(() => { if (msg.textContent.includes("已複製端點")) msg.textContent = ""; }, 2000);
      });
    });
  }

  const MODE_HINT = {
    auto: "直連優先，分頁備援",
    direct: "僅 Cookie 直連（不支援 ChatGPT）",
    extension: "瀏覽器分頁轉發",
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
      if (mode === "direct" && !d.direct_configured) extra = "（未設定 Cookie）";
      if (mode === "extension" && !d.browser_connected) extra = "（未連線分頁）";
      paintTransport(mode, extra);
    } catch (_) {
      if (transportHint) transportHint.textContent = "伺服器未啟動";
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
          msg.textContent = "模式已切換：" + (d.mode || mode);
          msg.className = "msg ok";
        } catch (e) {
          if (transportHint) transportHint.textContent = "切換失敗：" + (e.message || e);
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
      msg.textContent = "設定已儲存";
      msg.className = "msg ok";
      setTimeout(() => { if (msg.textContent.includes("設定已儲存")) msg.textContent = ""; }, 2000);
    });
  };

  if (chkClean) chkClean.addEventListener("change", saveSettings);
  if (chkAutoDismiss) chkAutoDismiss.addEventListener("change", saveSettings);

  // 3. Detect current tab
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs || tabs.length === 0) return;
    const url = tabs[0].url || "";
    if (url.includes("chatgpt.com")) {
      setTabStatus(true, "<strong>ChatGPT Web</strong> 就緒");
    } else if (url.includes("gemini.google.com")) {
      setTabStatus(true, "<strong>Gemini Web</strong> 就緒");
    } else if (url.includes("deepseek.com")) {
      setTabStatus(true, "<strong>DeepSeek Web</strong> 就緒");
    } else {
      setTabStatus(false, "未開啟支援分頁");
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
          maxTokens: 16384,
          contextWindow: 32768,
          supportsThinking: true,
        },
      };
      navigator.clipboard.writeText(JSON.stringify(configJson, null, 2)).then(() => {
        msg.textContent = "已複製 IDE 配置";
        msg.className = "msg ok";
        setTimeout(() => { if (msg.textContent.includes("已複製 IDE 配置")) msg.textContent = ""; }, 2000);
      }).catch(() => {
        msg.textContent = "複製失敗，請手動複製端點。";
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
          msg.innerHTML = "已同步 Cookie 至本機（已複製）";
          msg.className = "msg ok";
        } else {
          msg.textContent = "Cookie 已複製（本機伺服器未啟動）";
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

  if (btnCleaner) {
    btnCleaner.addEventListener("click", async () => {
      btnCleaner.disabled = true;
      msg.textContent = "正在啟動批次刪除…";
      msg.className = "msg";
      try {
        const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
        const tab = tabs && tabs[0];
        const url = (tab && tab.url) || "";
        if (!tab || !url.includes("gemini.google.com")) {
          throw new Error("請先開啟 gemini.google.com 分頁（批次刪除僅支援 Gemini）");
        }
        await chrome.tabs.sendMessage(tab.id, { type: "w2l-cleaner-start", autostart: false });
        msg.textContent = "批次刪除面板已在分頁右上角開啟";
        msg.className = "msg ok";
      } catch (e) {
        const raw = (e && e.message) ? e.message : String(e);
        if (/receiving end does not exist|receiving end|no receiving end/i.test(raw)) {
          msg.textContent = "分頁尚未載入擴充套件，請重新整理 Gemini 分頁後重試";
        } else {
          msg.textContent = raw;
        }
        msg.className = "msg err";
      } finally {
        btnCleaner.disabled = false;
      }
    });
  }

  if (btnDeepseek) {
    btnDeepseek.addEventListener("click", async () => {
      btnDeepseek.disabled = true;
      msg.textContent = "正在讀取 DeepSeek Token…";
      msg.className = "msg";
      try {
        const token = await fetchDeepSeekTokenFromPage();
        const payload = JSON.stringify({ token, source: "extension-popup" }, null, 2);

        // Auto copy to clipboard as backup (deepseek_token.json format)
        try { await navigator.clipboard.writeText(payload); } catch (_) {}

        // Try syncing to local server
        msg.textContent = "正在同步至本地伺服器...";
        let syncedToServer = false;
        try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 2000);
          const resp = await fetch("http://127.0.0.1:8765/v1/deepseek/token", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: payload,
            signal: controller.signal,
          });
          clearTimeout(timeoutId);
          if (resp.ok) syncedToServer = true;
        } catch (_) {
          syncedToServer = false;
        }

        if (syncedToServer) {
          msg.innerHTML = "已同步 Token 至本機（已複製）";
          msg.className = "msg ok";
        } else {
          msg.textContent = "Token 已複製（本機伺服器未啟動）";
          msg.className = "msg ok";
        }
      } catch (e) {
        msg.textContent = `${e.message || e}`;
        msg.className = "msg err";
      } finally {
        btnDeepseek.disabled = false;
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

// NOTE: serialized into the page via chrome.scripting.executeScript(world="MAIN"),
// so it must stay fully self-contained (no outer closures).
function readDeepSeekTokenMainWorld() {
  try {
    const raw = window.localStorage.getItem("userToken");
    if (!raw) return { ok: false, error: "NOT_FOUND" };
    try {
      const obj = JSON.parse(raw);
      const v = obj && (obj.value || obj.token || obj.userToken);
      if (v && String(v).trim()) return { ok: true, token: String(v).trim() };
      return { ok: false, error: "NO_VALUE" };
    } catch (_) {
      if (raw.trim()) return { ok: true, token: raw.trim() };
      return { ok: false, error: "PARSE_FAIL" };
    }
  } catch (e) {
    return { ok: false, error: "ACCESS_DENIED:" + ((e && e.message) || e) };
  }
}

async function fetchDeepSeekTokenFromPage() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs && tabs[0];
  const url = (tab && tab.url) || "";
  if (!tab || !url.includes("deepseek.com")) {
    throw new Error("請先開啟 https://chat.deepseek.com/a/chat/ 並登入，再點擊此按鈕");
  }
  let results;
  try {
    results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: "MAIN",
      func: readDeepSeekTokenMainWorld,
    });
  } catch (e) {
    throw new Error("無法讀取分頁內容（請確認已授權此網站）： " + (e.message || e));
  }
  const r = results && results[0] && results[0].result;
  if (!r || !r.ok || !r.token) {
    if (r && r.error === "NOT_FOUND") {
      throw new Error("找不到 userToken，請確認已在該分頁登入 DeepSeek 後重試");
    }
    throw new Error("讀取 userToken 失敗（" + ((r && r.error) || "unknown") + "），請重新登入後重試");
  }
  return r.token;
}
