/**
 * WebChat to Local Bridge - Main Content Script
 * Connects gemini.google.com and chatgpt.com to the local Python gateway and MCP engine.
 */

let ws = null;
let reconnectTimer = null;
let activeTurnId = null;
let isGeneratingResponse = false;
let rawForwarded = false;
let lastApiTurnTimestamp = 0;
const TURN_DEADLINE_MS = 120000;
const pendingMcpCalls = new Map();

const isChatGPT = window.location.hostname.includes("chatgpt.com");
const isGemini = window.location.hostname.includes("gemini.google.com");
const currentPlatform = isChatGPT ? "chatgpt" : (isGemini ? "gemini" : "unknown");

function getActiveController() {
  if (isChatGPT) return window.ChatGptController;
  return window.GeminiController;
}

function getActiveExtractor() {
  if (isChatGPT) return window.ChatGptExtractor;
  return window.GeminiExtractor;
}

function getStoredSettings() {
  return new Promise((resolve) => {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get({
        autoReload: isChatGPT, // Default true for ChatGPT guest mode
        forceNewChat: true,
        autoDismissModals: true
      }, resolve);
    } else {
      resolve({ autoReload: isChatGPT, forceNewChat: true, autoDismissModals: true });
    }
  });
}

function callLocalMcpTool(toolName, args) {
  return new Promise((resolve, reject) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return reject(new Error("WebSocket to WebChat2Local is not connected"));
    }
    const callId = "mcp_" + Math.random().toString(36).substring(2, 10);
    const timer = setTimeout(() => {
      pendingMcpCalls.delete(callId);
      reject(new Error(`MCP tool '${toolName}' call timed out after 60s`));
    }, 60000);

    pendingMcpCalls.set(callId, { resolve, reject, timer, toolName });
    ws.send(JSON.stringify({
      type: "call_mcp_tool",
      call_id: callId,
      tool: toolName,
      arguments: args || {}
    }));
    console.log(`[WebChat Tunnel] Dispatched MCP tool '${toolName}' to local bridge (id=${callId})`);
  });
}

// Window message listener for MAIN-world interceptor (used on Gemini)
window.addEventListener("message", (event) => {
  if (event.source !== window || !event.data || event.data.source !== "webchat2local-network") return;

  const msg = event.data;
  if (msg.type === "W2L_INTERCEPTOR_PONG") {
    console.log(`[WebChat Bridge] MAIN-world interceptor ready (${msg.version}).`);
    return;
  }

  if (!activeTurnId) return;
  if (msg.request_id && msg.request_id !== activeTurnId) return;

  if (msg.type === "capture_attempt") {
    console.log(`[WebChat Bridge][LOCAL-TRACE] capture_attempt turn=${activeTurnId} transport=${msg.transport || "?"} rpcids=${msg.rpcids || "-"}`);
    return;
  }

  if (msg.type === "chunk" && typeof msg.accumulated === "string" && msg.accumulated.length > 0) {
    const delta = typeof msg.delta === "string" ? msg.delta : "";
    rawForwarded = true;
    if (delta.length > 0 && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "chunk",
        turn_id: activeTurnId,
        text: msg.accumulated,
        delta,
        thought: "",
        thought_delta: "",
      }));
    }
    return;
  }

  if (msg.type === "stream_error") {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "error", turn_id: activeTurnId, error: msg.error || "Network stream error" }));
    }
    return;
  }

  if (msg.type === "done") {
    if (typeof msg.full_text === "string" && msg.full_text.trim().length > 0) {
      rawForwarded = true;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: "done",
          turn_id: activeTurnId,
          text: msg.full_text,
          thought: "",
        }));
      }
      isGeneratingResponse = false;
    }
  }
});

function init() {
  if (window.GeminiStatusHUD) {
    window.GeminiStatusHUD.init();
  }
  connectWebSocket();

  // Watch for in-page chat completions to execute in-page MCP Tunnel (Gemini only)
  if (isGemini) {
    let lastObservedResponse = null;
    let observerDebounce = null;
    const observer = new MutationObserver(() => {
      if (isGeneratingResponse || activeTurnId) return;
      if (Date.now() - lastApiTurnTimestamp < 300000) return;
      if (observerDebounce) clearTimeout(observerDebounce);
      observerDebounce = setTimeout(() => {
        const controller = getActiveController();
        const isGen = controller ? controller.isGenerating() : false;
        const extractor = getActiveExtractor();
        if (!isGen && extractor) {
          const respEl = extractor.findCurrentTurnResponseElement();
          if (respEl && respEl !== lastObservedResponse) {
            lastObservedResponse = respEl;
            runInPageMcpTunnelLoop(respEl);
          }
        }
      }, 500);
    });

    try {
      observer.observe(document.body, { childList: true, subtree: true });
    } catch (_) {}
  }
}

function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return;
  }

  try {
    ws = new WebSocket("ws://127.0.0.1:8765/ws");

    ws.onopen = () => {
      console.log(`[WebChat Bridge] WebSocket Connected to 127.0.0.1:8765 (${currentPlatform})`);
      if (window.GeminiStatusHUD) window.GeminiStatusHUD.setConnected();

      ws.send(JSON.stringify({
        type: "ready",
        meta: {
          url: window.location.href,
          platform: currentPlatform,
          model: isChatGPT ? "ChatGPT Web (Guest)" : "Google Gemini Web",
        }
      }));
    };

    ws.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleIncomingMessage(msg);
      } catch (err) {
        console.error("[WebChat Bridge] Error parsing WS message:", err);
      }
    };

    ws.onclose = () => {
      if (window.GeminiStatusHUD) window.GeminiStatusHUD.setDisconnected();
      scheduleReconnect();
    };

    ws.onerror = () => {
      if (window.GeminiStatusHUD) window.GeminiStatusHUD.setDisconnected();
      ws.close();
    };
  } catch (err) {
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connectWebSocket, 2000);
}

async function handleIncomingMessage(msg) {
  if (msg.type === "ping") {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "pong" }));
    }
    return;
  }

  if (msg.type === "mcp_tool_result") {
    const callId = msg.call_id;
    if (pendingMcpCalls.has(callId)) {
      const { resolve, timer, toolName } = pendingMcpCalls.get(callId);
      clearTimeout(timer);
      pendingMcpCalls.delete(callId);
      console.log(`[WebChat Tunnel] Received MCP tool result for '${toolName}' (id=${callId})`);
      resolve(msg.result);
    }
    return;
  }

  if (msg.type === "cancel_turn" || msg.type === "reset") {
    console.log("[WebChat Bridge] Received cancel/reset command.");
    isGeneratingResponse = false;
    activeTurnId = null;
    try {
      const stopBtns = document.querySelectorAll("button[aria-label*='Stop'], button[aria-label*='停止'], [data-testid='stop-button'], .stop-button");
      stopBtns.forEach(b => { if (b.offsetParent !== null) b.click(); });
    } catch (_) {}
    if (window.GeminiStatusHUD) window.GeminiStatusHUD.setConnected();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "reset_ack" }));
    }
    return;
  }

  if (msg.type === "submit_prompt") {
    const turnId = msg.turn_id;
    const promptText = msg.prompt;
    const model = msg.model || (isChatGPT ? "chatgpt-web/gpt-4o-mini" : "gemini-web/pro");

    const controller = getActiveController();
    const extractor = getActiveExtractor();

    if (!controller || !extractor) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: "error",
          turn_id: turnId,
          error: `無法載入控制器 (${currentPlatform})，請確認擴充套件已正確載入腳本。`
        }));
      }
      return;
    }

    // Auto-recovery & turn sequencing
    if (isGeneratingResponse || activeTurnId) {
      const isStillGenerating = controller.isGenerating ? controller.isGenerating() : false;
      if (!isStillGenerating) {
        isGeneratingResponse = false;
        activeTurnId = null;
      } else {
        console.warn("[WebChat Bridge] Previous turn still generating on webpage, waiting...");
        let cleared = false;
        for (let i = 0; i < 40; i++) {
          await sleep(100);
          if (!controller.isGenerating()) {
            cleared = true;
            break;
          }
        }
        if (cleared) {
          isGeneratingResponse = false;
          activeTurnId = null;
        } else {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: "error",
              turn_id: turnId,
              error: "已有對話正在執行；為避免頁面競態，已拒絕本次要求。"
            }));
          }
          return;
        }
      }
    }

    activeTurnId = turnId;
    rawForwarded = false;

    // Arm MAIN-world interceptor if on Gemini
    if (isGemini) {
      try {
        window.postMessage({
          source: "webchat2local-content",
          type: "W2L_SET_ACTIVE_REQUEST",
          request_id: turnId,
        }, "*");
      } catch (_) {}
    }

    lastApiTurnTimestamp = Date.now();
    const isNewSession = msg.is_new_session !== false;
    const sessionTag = isNewSession ? "新任務" : "接續會話";

    if (window.GeminiStatusHUD) window.GeminiStatusHUD.setGenerating(turnId, model, sessionTag);

    const settings = await getStoredSettings();

    // Execution with single-retry on failure
    let attempt = 0;
    let turnSuccess = false;
    let lastError = null;

    while (attempt < 2 && !turnSuccess) {
      attempt++;
      try {
        // Step A: Auto-dismiss modals on ChatGPT guest mode
        if (settings.autoDismissModals && controller.dismissLoginModals) {
          controller.dismissLoginModals();
        }

        // Step B: New chat if requested or preferred
        if ((settings.forceNewChat || msg.force_new_chat) && controller.startNewChatIfAvailable) {
          console.log("[WebChat Bridge] Opening fresh chat before turn...");
          controller.startNewChatIfAvailable();
          await sleep(attempt === 1 ? 800 : 1500);
        }

        // Step C: Wait for idle & ready
        if (controller.waitForIdleAndReady) {
          await controller.waitForIdleAndReady(6000);
        }

        // Step D: Snapshot prior responses
        extractor.snapshotBeforeTurn(turnId);

        // Step E: Model switch if supported
        if (controller.switchModelIfAvailable) {
          await controller.switchModelIfAvailable(model);
        }

        // Step F: Inject prompt and click send
        await controller.submitPromptWithRetry(promptText);

        // Step G: Stream response
        await streamResponseTurn(turnId, promptText, controller, extractor);

        turnSuccess = true;
      } catch (err) {
        lastError = err;
        console.warn(`[WebChat Bridge] Attempt ${attempt} failed:`, err);
        if (attempt === 1) {
          console.log("[WebChat Bridge] Attempting auto-retry once after 1s debounce...");
          await sleep(1000);
        }
      }
    }

    // After turns finish
    try {
      if (isGemini) {
        window.postMessage({ source: "webchat2local-content", type: "W2L_CLEAR_ACTIVE_REQUEST" }, "*");
      }
    } catch (_) {}
    isGeneratingResponse = false;
    activeTurnId = null;

    if (!turnSuccess) {
      console.error("[WebChat Bridge] Turn execution failed after retry:", lastError);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: "error",
          turn_id: turnId,
          error: lastError.message || String(lastError),
        }));
      }
      if (window.GeminiStatusHUD) window.GeminiStatusHUD.setConnected();
    } else {
      // Step H: Mandatory single-turn reload if configured (for unlogged-in guest hygiene)
      if (settings.autoReload) {
        console.log("[WebChat Bridge] Auto Reload enabled. Cleaning up page state in 600ms...");
        setTimeout(() => {
          if (controller.reloadPageCleanly) {
            controller.reloadPageCleanly();
          } else {
            window.location.reload();
          }
        }, 600);
      }
    }
  }
}

async function streamResponseTurn(turnId, promptSnippet, controller, extractor) {
  isGeneratingResponse = true;
  const deadline = Date.now() + TURN_DEADLINE_MS;
  let lastText = "";
  let lastThought = "";
  let targetEl = null;

  console.log(`[WebChat Bridge] Waiting for turn ${turnId} to start on ${currentPlatform}...`);

  let turnStarted = false;
  for (let i = 0; i < 200; i++) {
    await sleep(100);

    // Check for error banners (Rate limit, Cloudflare, etc.)
    if (extractor.detectErrorBanner) {
      const errBanner = extractor.detectErrorBanner();
      if (errBanner) {
        throw new Error(`${currentPlatform.toUpperCase()} 介面顯示錯誤: ${errBanner}`);
      }
    } else {
      const domErr = document.querySelector("div[role='alert'], .error-message, [data-test-id*='error'], .toast-error, .banner-error");
      if (domErr && domErr.offsetParent !== null) {
        const errText = (domErr.innerText || "").trim();
        if (/發生錯誤|Something went wrong|error\s*\d+|無法處理|Too many requests/i.test(errText)) {
          throw new Error(`介面顯示錯誤: ${errText}`);
        }
      }
    }

    targetEl = extractor.findCurrentTurnResponseElement();
    const generating = controller.isGenerating();

    if (targetEl || generating) {
      turnStarted = true;
      break;
    }
  }

  if (!turnStarted && !targetEl) {
    throw new Error(`${currentPlatform.toUpperCase()} 尚未開始生成回應，請確認網頁輸入框或網路狀態。`);
  }

  // Phase 2: If generation started but container element is still loading, wait for it
  if (!targetEl) {
    for (let i = 0; i < 100; i++) {
      await sleep(100);
      targetEl = extractor.findCurrentTurnResponseElement();
      if (targetEl) break;
    }
  }

  let idleRounds = 0;
  const maxIdleRounds = isChatGPT ? 15 : 12; // 15 * 80ms = 1.2s stabilization debounce

  // Phase 3: Pure DOM-centric streaming
  while (isGeneratingResponse) {
    if (Date.now() >= deadline) throw new Error(`回應逾時 (${TURN_DEADLINE_MS / 1000}s)`);
    await sleep(80);

    if (rawForwarded && !isGeneratingResponse) break;

    if (!targetEl) {
      targetEl = extractor.findCurrentTurnResponseElement();
    }
    if (!targetEl) {
      continue;
    }

    const state = extractor.extractCurrentState(targetEl);
    const currentCandidateText = state.text || "";
    const currentCandidateThought = state.thought || "";

    const deltaText = currentCandidateText.slice(lastText.length);
    const deltaThought = currentCandidateThought.slice(lastThought.length);

    if (deltaText.length > 0 || deltaThought.length > 0) {
      idleRounds = 0;
      if (!rawForwarded && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: "chunk",
          turn_id: turnId,
          text: currentCandidateText,
          delta: deltaText,
          thought: currentCandidateThought,
          thought_delta: deltaThought,
        }));
      }
      lastText = currentCandidateText;
      lastThought = currentCandidateThought;
    } else {
      const isGen = controller.isGenerating();
      const hasActionButtons = isChatGPT && targetEl && !!targetEl.querySelector("button[data-testid*='copy'], button[aria-label*='Copy'], button[aria-label*='複製']");
      if ((!isGen || hasActionButtons) && (lastText.length > 0 || lastThought.length > 0)) {
        idleRounds += (hasActionButtons ? 3 : 1);
        if (idleRounds >= maxIdleRounds) {
          break;
        }
      }
    }
  }

  if (rawForwarded) {
    if (window.GeminiStatusHUD) window.GeminiStatusHUD.setConnected();
    return;
  }

  if (lastText.trim().length === 0) {
    throw new Error("生成完畢，但未能擷取到文字回應。");
  }

  // Phase 4: Emit completion
  isGeneratingResponse = false;
  activeTurnId = null;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "done",
      turn_id: turnId,
      text: lastText,
      thought: lastThought,
    }));
  }

  console.log(`[WebChat Bridge] Turn ${turnId} completed (${lastText.length} chars).`);
  if (window.GeminiStatusHUD) window.GeminiStatusHUD.setConnected();
}

/**
 * Extract tool calls from text response for in-page MCP Tunnel (Gemini only)
 */
function extractInPageToolCalls(text) {
  const tools = [];
  if (!text || typeof text !== "string") return tools;

  const jsonMatches = [...text.matchAll(/<tool_call>([\s\S]*?)<\/tool_call>/gi)];
  for (const match of jsonMatches) {
    try {
      const parsed = JSON.parse(match[1].trim());
      if (parsed.name) {
        tools.push({
          name: parsed.name,
          arguments: parsed.arguments || parsed.parameters || parsed.input || {}
        });
      }
    } catch (_) {}
  }
  return tools;
}

async function runInPageMcpTunnelLoop(responseEl) {
  if (!responseEl || isGeneratingResponse || activeTurnId) return;
  const extractor = getActiveExtractor();
  const state = extractor ? extractor.extractCurrentState(responseEl) : null;
  const text = state ? state.text : (responseEl.innerText || "");
  const toolCalls = extractInPageToolCalls(text);

  if (toolCalls.length === 0) return;

  for (const tc of toolCalls) {
    try {
      if (window.GeminiStatusHUD) {
        window.GeminiStatusHUD.setStatus("generating", `🔧 [Tunnel MCP] 執行 ${tc.name}...`);
      }
      const result = await callLocalMcpTool(tc.name, tc.arguments);
      const resultText = `<tool_result name="${tc.name}">\n${typeof result === "object" ? JSON.stringify(result, null, 2) : String(result)}\n</tool_result>`;
      
      await sleep(500);
      const controller = getActiveController();
      if (controller) {
        const editor = controller.setInputText(resultText);
        await sleep(300);
        controller.clickSendButton(editor);
        if (window.GeminiStatusHUD) {
          window.GeminiStatusHUD.setConnected(`✅ [Tunnel MCP] ${tc.name} 結果已送回`);
        }
      }
    } catch (err) {
      console.error(`[WebChat Tunnel] Failed to execute in-page MCP tool ${tc.name}:`, err);
    }
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Start content script
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
