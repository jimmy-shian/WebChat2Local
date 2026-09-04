document.addEventListener("DOMContentLoaded", () => {
  const btnCapture = document.getElementById("btn-capture");
  const btnCopyCookie = document.getElementById("btn-copy-cookie");
  const btnDownloadCookie = document.getElementById("btn-download-cookie");
  const btnCopyConfig = document.getElementById("btn-copy-config");
  const msg = document.getElementById("msg");

  if (btnCopyConfig) {
    btnCopyConfig.addEventListener("click", () => {
      const configJson = {
        apiProvider: "openai",
        openAiBaseUrl: "http://127.0.0.1:8765/v1",
        openAiApiKey: "sk-local",
        openAiModelId: "gemini-web/ultra",
        customModelInfo: {
          supportsPromptCache: false,
          maxTokens: 4096,
          contextWindow: 32768,
          supportsThinking: true,
        },
      };
      navigator.clipboard.writeText(JSON.stringify(configJson, null, 2)).then(() => {
        msg.textContent = "✅ 已複製 Kilo / Cline 配置 (ContextWindow: 32k)！";
        msg.className = "msg ok";
      }).catch(() => {
        msg.textContent = "複製失敗，請手動設定 Context Window 為 32k。";
        msg.className = "msg err";
      });
    });
  }

  if (btnCapture) {
    btnCapture.addEventListener("click", async () => {
      btnCapture.disabled = true;
      msg.textContent = "正在讀取 Cookie...";
      msg.className = "msg";
      try {
        const cookies = await fetchCurrentCookies();
        const jsonStr = JSON.stringify(cookies, null, 2);

        // 1. 自動複製到剪貼簿做為無伺服器時的保底
        try {
          await navigator.clipboard.writeText(jsonStr);
        } catch (_) {}

        // 2. 嘗試同步至本地伺服器 (若有執行 run_server.py)
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
          if (resp.ok) {
            syncedToServer = true;
          }
        } catch (fetchErr) {
          // 本地伺服器未啟動
          syncedToServer = false;
        }

        if (syncedToServer) {
          msg.innerHTML = "✅ 已成功抓取並寫入本地 <code>gemini_cookies.json</code>！";
          msg.className = "msg ok";
        } else {
          msg.innerHTML = "✅ <b>Cookie 已抓取並複製至剪貼簿！</b><br><span style='color:#38bdf8;'>（提示：本地 8765 伺服器未啟動，已為您複製 JSON，可直接貼上至專案的 gemini_cookies.json，或點擊下方「下載檔案」）</span>";
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

  if (btnDownloadCookie) {
    btnDownloadCookie.addEventListener("click", async () => {
      btnDownloadCookie.disabled = true;
      msg.textContent = "正在讀取 Cookie...";
      msg.className = "msg";
      try {
        const cookies = await fetchCurrentCookies();
        const jsonStr = JSON.stringify(cookies, null, 2);
        const blob = new Blob([jsonStr], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "gemini_cookies.json";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        msg.textContent = "✅ 已下載 gemini_cookies.json，請移動至專案根目錄！";
        msg.className = "msg ok";
      } catch (e) {
        msg.textContent = `❌ ${e.message || e}`;
        msg.className = "msg err";
      } finally {
        btnDownloadCookie.disabled = false;
      }
    });
  }
});

async function fetchCurrentCookies() {
  const onePsid = await getCookie("__Secure-1PSID");
  const onePsidts = await getCookie("__Secure-1PSIDTS");

  if (!onePsid) {
    throw new Error("找不到 __Secure-1PSID，請先在瀏覽器分頁登入 https://gemini.google.com");
  }

  return {
    "1psid": onePsid,
    "1psidts": onePsidts || "",
  };
}

async function getCookie(name) {
  // 1. 優先嘗試 gemini.google.com
  let val = await new Promise((resolve) => {
    chrome.cookies.get({ url: "https://gemini.google.com", name }, (cookie) => {
      resolve(cookie ? cookie.value : "");
    });
  });
  if (val) return val;

  // 2. 備用嘗試 google.com
  val = await new Promise((resolve) => {
    chrome.cookies.get({ url: "https://google.com", name }, (cookie) => {
      resolve(cookie ? cookie.value : "");
    });
  });
  if (val) return val;

  // 3. 通用 domain 比對
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

