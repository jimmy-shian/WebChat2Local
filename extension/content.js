/**
 * WebChat2Local Content Script (v3.2.0 - Raw Network First Architecture)
 * Unified Gateway Coordinator connecting Browser Extensions to Local API Server.
 *
 * Data flow per request:
 *   1. Server -> WS -> content.js : chat_request
 *   2. content.js -> MAIN world   : W2L_SET_ACTIVE_REQUEST (tag the stream)
 *   3. content.js submits prompt via provider (typing + click)
 *   4. network_interceptor.js (MAIN world) captures the RAW SSE stream and
 *      postMessage's pristine chunks (XML tool tags INTACT) back here.
 *   5. content.js forwards raw chunks to the server.
 *   6. If no raw stream arrives within RAW_STREAM_TIMEOUT_MS, fall back to
 *      DOM polling via provider.extractResponse (Markdown-serialized).
 *
 * v3.2.0 fixes:
 *   - Single-sender guarantee: raw chunks are forwarded exactly once (either by
 *     the message listener OR the poll timer, never both) -> no duplicated text.
 *   - No raw/DOM mixing: once raw network data is received, DOM polling is
 *     disabled entirely for that request (DOM text used to corrupt Markdown).
 *   - Disarms the interceptor after each request (W2L_CLEAR_ACTIVE_REQUEST).
 */

(function () {
  const WS_URL = "ws://127.0.0.1:8765/ws";
  const RAW_STREAM_TIMEOUT_MS = 8000; // wait this long for raw network data before DOM fallback
  let socket = null;
  let activeRequestsCount = 0;
  let currentProvider = null;

  function detectProvider() {
    if (typeof DeepSeekProvider !== "undefined" && DeepSeekProvider.isMatch()) {
      return DeepSeekProvider;
    }
    if (typeof GeminiProvider !== "undefined" && GeminiProvider.isMatch()) {
      return GeminiProvider;
    }
    if (typeof ChatGPTProvider !== "undefined" && ChatGPTProvider.isMatch()) {
      return ChatGPTProvider;
    }
    return null;
  }

  currentProvider = detectProvider();
  console.log(`[WebChat2Local v3.3.0] Initialized with provider: ${currentProvider ? currentProvider.name : "None"}`);

  const MAX_CONNECT_RETRIES = 3;
  let connectAttempts = 0;
  let reconnectTimeoutId = null;

  window.WebChat2LocalBridge = {
    status: "disconnected",
    activeRequests: 0,
    userInfo: null,
    retryCount: 0,
    maxRetries: MAX_CONNECT_RETRIES,
    retryExhausted: false,
    listeners: [],
    notify: function () {
      this.listeners.forEach((fn) => {
        try { fn(this); } catch (e) {}
      });
    },
    retry: function () {
      console.log("[WebChat2Local] 手動觸發重新連線...");
      connectWebSocket(true);
    },
  };

  /* ------------------------------------------------------------------ *
   *  WebSocket connection management
   * ------------------------------------------------------------------ */

  function handleDisconnect() {
    socket = null;

    if (connectAttempts < MAX_CONNECT_RETRIES) {
      window.WebChat2LocalBridge.status = "connecting";
      window.WebChat2LocalBridge.retryExhausted = false;
      window.WebChat2LocalBridge.retryCount = connectAttempts;
      window.WebChat2LocalBridge.notify();

      if (!reconnectTimeoutId) {
        reconnectTimeoutId = setTimeout(() => {
          reconnectTimeoutId = null;
          connectWebSocket(false);
        }, 3000);
      }
    } else {
      console.warn(`[WebChat2Local] 已嘗試連線 ${MAX_CONNECT_RETRIES} 次皆無法連線至本地伺服器，已停止自動重試。`);
      window.WebChat2LocalBridge.status = "disconnected";
      window.WebChat2LocalBridge.retryExhausted = true;
      window.WebChat2LocalBridge.retryCount = connectAttempts;
      window.WebChat2LocalBridge.notify();
    }
  }

  function connectWebSocket(isManual = false) {
    if (reconnectTimeoutId) {
      clearTimeout(reconnectTimeoutId);
      reconnectTimeoutId = null;
    }

    if (isManual) {
      connectAttempts = 0;
      window.WebChat2LocalBridge.retryExhausted = false;
    }

    if (socket) {
      if (socket.readyState === WebSocket.OPEN) {
        return;
      }
      if (socket.readyState === WebSocket.CONNECTING && !isManual) {
        return;
      }
      try {
        socket.close();
      } catch (e) {}
      socket = null;
    }

    connectAttempts++;
    window.WebChat2LocalBridge.retryCount = connectAttempts;
    window.WebChat2LocalBridge.retryExhausted = false;
    window.WebChat2LocalBridge.status = "connecting";
    window.WebChat2LocalBridge.notify();

    console.log(`[WebChat2Local] 正在連線至本地伺服器 (嘗試 ${connectAttempts}/${MAX_CONNECT_RETRIES})...`);

    try {
      socket = new WebSocket(WS_URL);

      socket.onopen = async () => {
        console.log(`[WebChat2Local] WebSocket connected for ${currentProvider ? currentProvider.name : "Browser"}.`);
        connectAttempts = 0;
        window.WebChat2LocalBridge.retryCount = 0;
        window.WebChat2LocalBridge.retryExhausted = false;
        window.WebChat2LocalBridge.status = "connected";
        window.WebChat2LocalBridge.notify();

        let info = { email: "AI Web User", plan: "Free", provider: currentProvider ? currentProvider.name : "Unknown" };
        if (currentProvider) {
          try {
            info = await currentProvider.getUserInfo();
            window.WebChat2LocalBridge.userInfo = info;
          } catch (e) {}
        }

        socket.send(
          JSON.stringify({
            type: "ready",
            info: info,
          })
        );
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "chat_request") {
            handleChatRequest(data);
          } else if (data.type === "ping") {
            socket.send(JSON.stringify({ type: "pong" }));
          }
        } catch (e) {
          console.error("[WebChat2Local] WS message error:", e);
        }
      };

      socket.onclose = () => {
        handleDisconnect();
      };

      socket.onerror = () => {};
    } catch (e) {
      handleDisconnect();
    }
  }

  /* ------------------------------------------------------------------ *
   *  Prompt formatting
   * ------------------------------------------------------------------ */

  /**
   * Builds the XML tool-calling instruction block appended to the prompt when
   * the client (Cline / Roo Code) declares tools. Without this, the web model
   * has no idea it should answer with XML tool tags and will reply
   * "I don't have file tools" instead.
   */
  function buildToolInstruction(tools) {
    if (!tools || tools.length === 0) return "";

    let tools_str = "";
    for (const t of tools) {
      const name = t.name || "";
      const params = (t.parameters && t.parameters.properties) ? Object.keys(t.parameters.properties) : [];
      const paramList = params.map(k => `"${k}": "..."`).join(", ");
      tools_str += `- ${name}: {"tool": "${name}", "arguments": {${paramList}}}\n`;
    }

    return [
      "【可用工具與 JSON 呼叫格式】",
      "你是一個專業的任務執行 AI。當需要執行動作時，必須輸出 JSON 工具呼叫格式：",
      "```json",
      '{"tool": "tool_name", "arguments": {"param1": "value1"}}',
      "```",
      "",
      "可用工具清單：",
      tools_str,
      "【絕對執行規則】",
      "1. 若需執行指令或操作檔案，【直接】輸出對應工具的 JSON 格式。",
      "2. 若使用者僅進行純問答，不需使用工具，請直接用文字回答。",
      "3. 每次回覆【最多只能】輸出一個工具呼叫。執行後等待結果。",
      "4. 當所有任務完成時，使用 `attempt_completion` 工具總結。",
      "5. 若要修改檔案，請先使用讀取檔案工具獲取內容與版本號，再進行修改。",
      "6. 嚴禁在動作未完成前呼叫 `attempt_completion`。"
    ].join("\n");
  }

  /**
   * Extracts the last user message text for DOM-matching (the formatted prompt
   * starts with the tool instruction, which never appears in the page DOM).
   */
  function lastUserSnippet(messages) {
    if (!messages || messages.length === 0) return "";
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        const c = messages[i].content;
        const text = typeof c === "string" ? c : JSON.stringify(c);
        return text.slice(0, 30).trim();
      }
    }
    return "";
  }

  function formatMessagesPrompt(messages, tools) {
    if (!messages || messages.length === 0) return "";

    let conversationTurns = [];
    let customSystemNote = "";

    // Automated client validation phrases to filter out so model doesn't fall into apology loops
    const AUTO_ERROR_PATTERNS = [
      /\[ERROR\]\s*You did not use a tool/i,
      /# Reminder:\s*Instructions for Tool Use/i,
      /<environment_details>[\s\S]*?<\/environment_details>/i,
      /Please share this file with .*? Support/i,
    ];

    for (const msg of messages) {
      const role = msg.role;
      let text = typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content);
      if (!text || text.trim() === "") continue;

      if (role === "system") {
        customSystemNote = text.trim();
      } else if (role === "user") {
        const isAutoError = AUTO_ERROR_PATTERNS.some((p) => p.test(text));
        if (!isAutoError) {
          const cleanedText = text.replace(/<environment_details>[\s\S]*?<\/environment_details>/gi, "").trim();
          if (cleanedText) {
            conversationTurns.push({ role: "User", text: cleanedText });
          }
        }
      } else if (role === "assistant") {
        conversationTurns.push({ role: "Assistant", text: text.trim() });
      } else {
        conversationTurns.push({ role: role, text: text.trim() });
      }
    }

    let formattedParts = [];
    if (customSystemNote) {
      formattedParts.push(customSystemNote);
    }

    if (conversationTurns.length === 1 && conversationTurns[0].role === "User") {
      formattedParts.push(conversationTurns[0].text);
    } else {
      for (const turn of conversationTurns) {
        formattedParts.push(`[${turn.role}]:\n${turn.text}`);
      }
    }

    const toolHeader = buildToolInstruction(tools);
    if (toolHeader) {
      return toolHeader + "\n\n" + formattedParts.join("\n\n");
    }
    return formattedParts.join("\n\n");
  }

  /* ------------------------------------------------------------------ *
   *  Raw network stream bridge (MAIN world <-> content script)
   * ------------------------------------------------------------------ */

  // Active capture session for the current request.
  let rawCapture = null;

  window.addEventListener("message", (event) => {
    if (event.source !== window || !event.data) return;
    if (event.data.source !== "webchat2local-network") return;

    const msg = event.data;

    // Version handshake (no request_id) - handle before the request filter.
    if (msg.type === "W2L_INTERCEPTOR_PONG") {
      console.log(`[WebChat2Local] MAIN-world interceptor alive, version: ${msg.version}`);
      return;
    }

    if (!rawCapture) return; // stray stream (user typing manually) - ignore

    // Diagnostics: report capture attempts to the server log.
    if (msg.type === "capture_attempt") {
      console.log(`[WebChat2Local] Network stream matched: ${msg.url} (gated: ${msg.gated})`);
      return;
    }

    if (msg.request_id !== rawCapture.reqId) return; // stale stream from a previous request

    if (msg.type === "chunk") {
      // Single-sender guarantee: the listener is the ONLY place raw deltas are
      // forwarded. The poll timer only inspects rawCapture state for completion.
      rawCapture.receivedRaw = true;
      rawCapture.fullText = msg.accumulated || (rawCapture.fullText + msg.delta);
      rawCapture.lastActivity = Date.now();
      sendChunkMessage(rawCapture.reqId, msg.delta, rawCapture.fullText);
    } else if (msg.type === "done") {
      rawCapture.receivedRaw = true;
      rawCapture.fullText = msg.full_text || rawCapture.fullText;
      rawCapture.done = true;
      rawCapture.lastActivity = Date.now();
    }
  });

  /* ------------------------------------------------------------------ *
   *  Request handling
   * ------------------------------------------------------------------ */

  async function handleChatRequest(job) {
    const reqId = job.request_id;
    activeRequestsCount++;
    window.WebChat2LocalBridge.activeRequests = activeRequestsCount;
    window.WebChat2LocalBridge.notify();

    const promptText = formatMessagesPrompt(job.messages, job.tools);
    const promptSnippet = lastUserSnippet(job.messages);

    if (!currentProvider) {
      currentProvider = detectProvider();
    }

    if (!currentProvider) {
      sendErrorMessage(reqId, "未識別到支援的 AI 網頁版（支援 DeepSeek、ChatGPT 與 Google Gemini）");
      activeRequestsCount = Math.max(0, activeRequestsCount - 1);
      return;
    }

    const MAX_RETRIES = 2;
    let lastError = null;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      // Arm the raw-network capture BEFORE submitting so the interceptor
      // tags the very next conversation stream with our request id.
      rawCapture = {
        reqId: reqId,
        fullText: "",
        receivedRaw: false,
        done: false,
        lastActivity: Date.now(),
      };
      window.postMessage({ type: "W2L_SET_ACTIVE_REQUEST", request_id: reqId }, "*");

      // Verify the MAIN-world interceptor is actually loaded (version handshake).
      window.postMessage({ type: "W2L_PING_INTERCEPTOR" }, "*");

      try {
        const result = await attemptSingleRequest(reqId, promptText, promptSnippet);
        if (result && result.length > 0) {
          sendDoneMessage(reqId, result);
          return; // Success
        }
        lastError = new Error("空回應");
      } catch (err) {
        lastError = err;
      } finally {
        rawCapture = null; // disarm capture session
        window.postMessage({ type: "W2L_CLEAR_ACTIVE_REQUEST" }, "*");
      }

      if (attempt < MAX_RETRIES) {
        console.log(`[WebChat2Local] Request ${reqId} attempt ${attempt + 1} returned empty. Retrying in 1s...`);
        await new Promise((r) => setTimeout(r, 1000));
      }
    }

    // All retries exhausted
    console.error(`[WebChat2Local] Request ${reqId} failed after ${MAX_RETRIES + 1} attempts:`, lastError);
    sendErrorMessage(reqId, lastError?.message || "多次重送後仍為空回應");
    activeRequestsCount = Math.max(0, activeRequestsCount - 1);
    window.WebChat2LocalBridge.activeRequests = activeRequestsCount;
    window.WebChat2LocalBridge.notify();
  }

  async function attemptSingleRequest(reqId, promptText, promptSnippet) {
    // 0. Snapshot the DOM BEFORE submitting so we can reject stale answers
    //    from the previous turn (they are still on screen when polling starts).
    let preSubmitText = "";
    try {
      preSubmitText = currentProvider.extractResponse("") || "";
    } catch (e) {}

    // 1. Set Input Text
    const inputEl = currentProvider.setInput(promptText);

    await new Promise((r) => setTimeout(r, 200));

    // 2. Submit Prompt
    currentProvider.submit(inputEl);

    // 3. Monitor Response Streaming
    let domText = "";
    let isDone = false;
    let lastStableTime = Date.now();
    const startTime = Date.now();

    return await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        clearInterval(pollTimer);
        const finalText = pickFinalText(domText);
        if (finalText && finalText.length > 0) {
          resolve(finalText);
        } else {
          reject(new Error(`${currentProvider.name} 網頁未在 180 秒內回應`));
        }
      }, 180000);

      const pollTimer = setInterval(() => {
        if (isDone) return;

        // ---- Raw network stream path (pristine XML preserved) ----
        // NOTE: chunk forwarding happens ONLY in the message listener above.
        // This timer never re-sends raw text (that used to duplicate output).
        if (rawCapture && rawCapture.receivedRaw) {
          const rawIdle = Date.now() - rawCapture.lastActivity;
          if (rawCapture.done && rawIdle > 500) {
            finish("raw");
            return;
          }
          // Raw stream went silent -> treat as complete. 10s tolerance so
          // long answers with slow/thinking pauses are not truncated.
          if (rawCapture.fullText.length > 0 && !rawCapture.done && rawIdle > 10000) {
            finish("raw-idle");
            return;
          }
          return; // raw active: DOM polling stays disabled (no mixing!)
        }

        // ---- DOM polling fallback path (only when NO raw data at all) ----
        const rawWaitElapsed = Date.now() - startTime > RAW_STREAM_TIMEOUT_MS;
        if (rawWaitElapsed) {
          const isGenerating = currentProvider.isGenerating();
          const currentDomText = currentProvider.extractResponse(promptSnippet);

          if (currentDomText && currentDomText.length > 0) {
            // Reject the PREVIOUS turn's answer: identical to the pre-submit
            // snapshot means the new answer has not started rendering yet.
            const isStale = preSubmitText && currentDomText === preSubmitText;
            if (!isStale && currentDomText.length > domText.length) {
              const prevLength = domText.length;
              domText = currentDomText;
              lastStableTime = Date.now();
              sendChunkMessage(reqId, currentDomText.slice(prevLength), currentDomText);
            }
          }

          // Finish when: text stopped growing for 1.5s AND generation ended,
          // OR text stopped growing for 6s (safety net if the stop-button
          // selector no longer matches the current UI).
          const stableFor = Date.now() - lastStableTime;
          if (domText.length > 0 && stableFor > 1500 && (!isGenerating || stableFor > 6000)) {
            finish("dom");
            return;
          }
        }
      }, 100);

      function finish(mode) {
        if (isDone) return;
        isDone = true;
        clearTimeout(timeout);
        clearInterval(pollTimer);

        const finalText = pickFinalText(domText);
        console.log(
          `[WebChat2Local] ${currentProvider.name} request ${reqId} complete via ${mode}. ` +
          `Total: ${finalText.length} chars. XML tags ${finalText.includes("<") ? "preserved" : "absent"}.`
        );
        resolve(finalText);
      }
    });
  }

  /**
   * Prefer the raw network text (contains XML tool tags). If it is empty,
   * fall back to whatever DOM polling collected.
   */
  function pickFinalText(domText) {
    if (rawCapture && rawCapture.fullText && rawCapture.fullText.length > 0) {
      return rawCapture.fullText;
    }
    return domText || "";
  }

  /* ------------------------------------------------------------------ *
   *  Server messaging
   * ------------------------------------------------------------------ */

  function sendChunkMessage(reqId, delta, accumulated) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(
        JSON.stringify({
          type: "chunk",
          request_id: reqId,
          delta: delta,
          accumulated: accumulated,
        })
      );
    }
  }

  function sendDoneMessage(reqId, fullText) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(
        JSON.stringify({
          type: "done",
          request_id: reqId,
          full_text: fullText,
          finish_reason: "stop",
        })
      );
    }
  }

  function sendErrorMessage(reqId, errMsg) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(
        JSON.stringify({
          type: "error",
          request_id: reqId,
          error: errMsg,
        })
      );
    }
  }

  let isManualDisconnected = false;

  function renderFloatingWidget() {
    let container = document.getElementById("w2l-floating-badge");
    if (!container) {
      container = document.createElement("div");
      container.id = "w2l-floating-badge";
      container.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        z-index: 999999;
        background: #18181b;
        color: #e4e4e7;
        padding: 6px 12px;
        border-radius: 8px;
        border: 1px solid #3f3f46;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
        user-select: none;
      `;
      document.body.appendChild(container);
    }

    const isConnected = socket && socket.readyState === WebSocket.OPEN && !isManualDisconnected;
    const statusText = isManualDisconnected ? "🔴 已自主斷線" : (isConnected ? "🟢 已連線" : "🟡 連線中...");
    const btnText = isManualDisconnected ? "連線" : "斷線";
    const btnColor = isManualDisconnected ? "#10b981" : "#ef4444";

    container.innerHTML = `
      <span style="font-weight:600;">⚡ W2L:</span>
      <span>${statusText}</span>
      <button id="w2l-toggle-btn" style="
        background: ${btnColor};
        color: #fff;
        border: none;
        padding: 2px 8px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 11px;
        font-weight: 500;
      ">${btnText}</button>
    `;

    const btn = document.getElementById("w2l-toggle-btn");
    if (btn) {
      btn.onclick = () => {
        if (isManualDisconnected) {
          isManualDisconnected = false;
          connectWebSocket(true);
        } else {
          isManualDisconnected = true;
          if (socket) {
            try { socket.close(); } catch(e) {}
            socket = null;
          }
          renderFloatingWidget();
        }
      };
    }
  }

  // Hook into notify
  const origNotify = window.WebChat2LocalBridge.notify;
  window.WebChat2LocalBridge.notify = function() {
    origNotify();
    renderFloatingWidget();
  };

  setInterval(renderFloatingWidget, 3000);
  window.addEventListener("DOMContentLoaded", renderFloatingWidget);
  setTimeout(renderFloatingWidget, 1000);

  connectWebSocket();
})();