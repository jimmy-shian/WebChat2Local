document.addEventListener("DOMContentLoaded", () => {
  const btnCapture = document.getElementById("btn-capture");
  const btnCopyCookie = document.getElementById("btn-copy-cookie");
  const btnCopyConfig = document.getElementById("btn-copy-config");
  const tabStatus = document.getElementById("tab-status");
  const msg = document.getElementById("msg");

  const chkAutoReload = document.getElementById("setting-auto-reload");
  const chkForceNewChat = document.getElementById("setting-force-new-chat");
  const chkAutoDismiss = document.getElementById("setting-auto-dismiss");

  // 1. Load preferences
  chrome.storage.local.get({
    autoReload: true,
    forceNewChat: true,
    autoDismissModals: true
  }, (res) => {
    if (chkAutoReload) chkAutoReload.checked = !!res.autoReload;
    if (chkForceNewChat) chkForceNewChat.checked = !!res.forceNewChat;
    if (chkAutoDismiss) chkAutoDismiss.checked = !!res.autoDismissModals;
  });

  // 2. Save on toggle
  const saveSettings = () => {
    chrome.storage.local.set({
      autoReload: chkAutoReload ? chkAutoReload.checked : true,
      forceNewChat: chkForceNewChat ? chkForceNewChat.checked : true,
      autoDismissModals: chkAutoDismiss ? chkAutoDismiss.checked : true
    }, () => {
      msg.textContent = "⚙️ 偏好設定已自動儲存";
      msg.className = "msg ok";
      setTimeout(() => { if (msg.textContent.includes("偏好設定")) msg.textContent = ""; }, 2000);
    });
  };

  if (chkAutoReload) chkAutoReload.addEventListener("change", saveSettings);
  if (chkForceNewChat) chkForceNewChat.addEventListener("change", saveSettings);
  if (chkAutoDismiss) chkAutoDismiss.addEventListener("change", saveSettings);

  // 3. Detect current tab
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs || tabs.length === 0) return;
    const url = tabs[0].url || "";
    if (url.includes("chatgpt.com")) {
      tabStatus.innerHTML = "🟢 當前分頁: <strong style='color:#10b981;'>ChatGPT Web (支援免登入)</strong>";
    } else if (url.includes("gemini.google.com")) {
      tabStatus.innerHTML = "🟢 當前分頁: <strong style='color:#3b82f6;'>Google Gemini Web</strong>";
    } else {
      tabStatus.innerHTML = "⚪ 當前非支援分頁（請開啟 <a href='https://chatgpt.com' target='_blank' style='color:#38bdf8;'>chatgpt.com</a> 或 <a href='https://gemini.google.com' target='_blank' style='color:#38bdf8;'>gemini.google.com</a>）";
    }
  });

  if (btnCopyConfig) {
    btnCopyConfig.addEventListener("click", () => {
      const configJson = {
        apiProvider: "openai",
        openAiBaseUrl: "http://127.0.0.1:8765/v1",
        openAiApiKey: "sk-local",
        openAiModelId: "gpt-4o-mini",
        customModelInfo: {
          supportsPromptCache: false,
          maxTokens: 4096,
          contextWindow: 32768,
          supportsThinking: true,
        },
      };
      navigator.clipboard.writeText(JSON.stringify(configJson, null, 2)).then(() => {
        msg.textContent = "✅ 已複製 IDE 配置 (預設 gpt-4o-mini / 8765)！";
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

        // Auto copy to clipboard
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
          msg.innerHTML = "✅ 已成功抓取並寫入本地 <code>gemini_cookies.json</code>！";
          msg.className = "msg ok";
        } else {
          msg.innerHTML = "✅ <b>Gemini Cookie 已複製至剪貼簿！</b><br><span style='color:#38bdf8;'>（提示：若未開伺服器，可直接貼入 gemini_cookies.json）</span>";
          msg.className = "msg ok";
        }
      } catch (e) {
        msg.textContent = `❌ ${e.message || e}`;
        msg.className = "msg err";
      } finally {
        btnCapture.disabled = false;
      }
    });
  }

  if (btnCopyCookie) {
    btnCopyCookie.addEventListener("click", async () => {
      btnCopyCookie.disabled = true;
      msg.textContent = "正在讀取 Cookie...";
      msg.className = "msg";
      try {
        const cookies = await fetchCurrentCookies();
        const jsonStr = JSON.stringify(cookies, null, 2);
        await navigator.clipboard.writeText(jsonStr);
        msg.textContent = "✅ 已複製 Cookie JSON！請直接貼上至 gemini_cookies.json";
        msg.className = "msg ok";
      } catch (e) {
        msg.textContent = `❌ ${e.message || e}`;
        msg.className = "msg err";
      } finally {
        btnCopyCookie.disabled = false;
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
