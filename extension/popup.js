document.addEventListener("DOMContentLoaded", () => {
  const btnCapture = document.getElementById("btn-capture");
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
          supportsThinking: true
        }
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
        const onePsid = await getCookie("__Secure-1PSID");
        const onePsidts = await getCookie("__Secure-1PSIDTS");

        if (!onePsid) {
          msg.textContent = "找不到 __Secure-1PSID，請先登入 gemini.google.com";
          msg.className = "msg err";
          return;
        }

        msg.textContent = "正在寫入本地...";
        const resp = await fetch("http://127.0.0.1:8765/v1/cookies", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ "1psid": onePsid, "1psidts": onePsidts }),
        });

        if (resp.ok) {
          msg.textContent = "✅ 已存入 gemini_cookies.json，直連模式已就緒";
          msg.className = "msg ok";
        } else {
          const body = await resp.text();
          msg.textContent = `寫入失敗 (HTTP ${resp.status}): ${body}`;
          msg.className = "msg err";
        }
      } catch (e) {
        msg.textContent = `錯誤: ${e.message || e}`;
        msg.className = "msg err";
      } finally {
        btnCapture.disabled = false;
      }
    });
  }
});

function getCookie(name) {
  return new Promise((resolve) => {
    chrome.cookies.get(
      { url: "https://gemini.google.com", name },
      (cookie) => resolve(cookie ? cookie.value : "")
    );
  });
}
