/**
 * Gemini Web to Local Bridge - Main Content Script
 * Connects gemini.google.com to the local Python gateway and MCP engine.
 */

let ws = null;
let reconnectTimer = null;
let activeTurnId = null;
let isGeneratingResponse = false;
let rawForwarded = false;
let lastApiTurnTimestamp = 0;
const TURN_DEADLINE_MS = 120000;
const pendingMcpCalls = new Map();

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
    console.log(`[Gemini Tunnel] Dispatched MCP tool '${toolName}' to local bridge (id=${callId})`);
  });
}

window.addEventListener("message", (event) => {
  if (event.source !== window || !event.data || event.data.source !== "webchat2local-network") return;

  const msg = event.data;
  if (msg.type === "W2L_INTERCEPTOR_PONG") {
    console.log(`[Gemini Bridge] MAIN-world interceptor ready (${msg.version}).`);
    return;
  }

  // The MAIN-world interceptor is explicitly armed for the current turn by
  // handleIncomingMessage().  Its request_id is the turn_id, so events can be
  // routed without guessing which network request belongs to which turn.
  if (!activeTurnId) return;
  if (msg.request_id && msg.request_id !== activeTurnId) return;

  if (msg.type === "capture_attempt") {
    console.log(`[Gemini Bridge][LOCAL-TRACE] capture_attempt turn=${activeTurnId} transport=${msg.transport || "?"} rpcids=${msg.rpcids || "-"}`);
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
      console.log(`[Gemini Bridge][LOCAL-TRACE] raw_chunk id=${activeTurnId} text_len=${msg.accumulated.length} delta_len=${delta.length}`);
    }
    return;
  }

  if (msg.type === "stream_error") {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "error", turn_id: activeTurnId, error: msg.error || "Gemini network stream error" }));
    }
    return;
  }

  if (msg.type === "done") {
    // An interceptor completion with no extracted answer is NOT authoritative;
    // keep the DOM path alive because the transport parser may intentionally
    // reject a frame that Gemini rendered successfully.
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
      // Leave the turn state intact until streamResponseTurn observes this
      // completion; its finally block owns the interceptor disarm/lock cleanup.
    }
  }
});

function init() {
  if (window.GeminiStatusHUD) {
    window.GeminiStatusHUD.init();
  }
  connectWebSocket();

  // Watch for manual chat completions on gemini.google.com to execute autonomous in-browser MCP Tunnel
  let lastObservedResponse = null;
  let observerDebounce = null;
  const observer = new MutationObserver(() => {
    if (isGeneratingResponse || activeTurnId) return;
    // Suppress in-page autonomous tool execution when API client (Kilo/Cline) is actively driving sessions
    if (Date.now() - lastApiTurnTimestamp < 300000) return;
    if (observerDebounce) clearTimeout(observerDebounce);
    observerDebounce = setTimeout(() => {
      const isGen = window.GeminiController ? window.GeminiController.isGenerating() : false;
      if (!isGen && window.GeminiExtractor) {
        const respEl = window.GeminiExtractor.findCurrentTurnResponseElement();
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

function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return;
  }

  try {
    ws = new WebSocket("ws://127.0.0.1:8765/ws");

    ws.onopen = () => {
      console.log("[Gemini Bridge] WebSocket Connected to 127.0.0.1:8765");
      if (window.GeminiStatusHUD) window.GeminiStatusHUD.setConnected();

      ws.send(JSON.stringify({
        type: "ready",
        meta: {
          url: window.location.href,
          model: "Google Gemini Web",
        }
      }));
      console.log("[Gemini Bridge][LOCAL-TRACE] ready sent", window.location.href);
    };

    ws.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleIncomingMessage(msg);
      } catch (err) {
        console.error("[Gemini Bridge] Error parsing WS message:", err);
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
      console.log(`[Gemini Tunnel] Received MCP tool result for '${toolName}' (id=${callId})`);
      resolve(msg.result);
    }
    return;
  }

  if (msg.type === "cancel_turn" || msg.type === "reset") {
    console.log("[Gemini Bridge] Received cancel/reset command.");
    isGeneratingResponse = false;
    activeTurnId = null;
    try {
      const stopBtns = document.querySelectorAll("button[aria-label*='Stop'], button[aria-label*='停止'], button[aria-label*='Stop generating'], .stop-button");
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
    const model = msg.model || "gemini-web/pro";

    // Auto-recovery & smooth turn sequencing
    if (isGeneratingResponse || activeTurnId) {
      const isStillGenerating = window.GeminiController ? window.GeminiController.isGenerating() : false;
      if (!isStillGenerating) {
        console.warn("[Gemini Bridge] Auto-clearing idle turn lock for new turn:", turnId);
        isGeneratingResponse = false;
        activeTurnId = null;
      } else {
        // If web page is still in progress, wait up to 4s for previous turn to finish generating
        console.warn("[Gemini Bridge] Previous turn still generating on webpage, waiting for completion...");
        let cleared = false;
        for (let i = 0; i < 40; i++) {
          await sleep(100);
          if (!window.GeminiController.isGenerating()) {
            cleared = true;
            break;
          }
        }
        if (cleared) {
          isGeneratingResponse = false;
          activeTurnId = null;
        } else {
          if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({
            type: "error", turn_id: turnId,
            error: "已有 Gemini request 正在執行（網頁端仍在生成中）；為避免 concurrent browser turns，已拒絕本次要求。"
          }));
          return;
        }
      }
    }
    activeTurnId = turnId;
    rawForwarded = false;

    // Arm the MAIN-world network interceptor BEFORE Gemini receives the
    // submitted prompt.  Without this handshake the interceptor's
    // activeRequestId remains null and it deliberately captures nothing.
    try {
      window.postMessage({
        source: "webchat2local-content",
        type: "W2L_SET_ACTIVE_REQUEST",
        request_id: turnId,
      }, "*");
      console.log(`[Gemini Bridge][LOCAL-TRACE] interceptor armed id=${turnId}`);
    } catch (_) {}

    lastApiTurnTimestamp = Date.now();
    const isNewSession = msg.is_new_session !== false;
    const sessionTag = isNewSession ? "新任務" : "接續會話";

    if (window.GeminiStatusHUD) window.GeminiStatusHUD.setGenerating(turnId, model, sessionTag);

    try {
      // 0. Only trigger new chat if explicitly requested via force_new_chat (avoid breaking ongoing tasks)
      if (msg.force_new_chat && window.GeminiController && window.GeminiController.startNewChatIfAvailable) {
        console.log("[Gemini Bridge] Explicit new chat requested; opening fresh chat on Gemini Web...");
        window.GeminiController.startNewChatIfAvailable();
        await sleep(1000);
      }

      // 1. Wait for screen / DOM state to be completely idle & ready before starting turn
      if (window.GeminiController.waitForIdleAndReady) {
        await window.GeminiController.waitForIdleAndReady(6000);
      }

      // IMPORTANT: mark the existing Gemini answers before submitting.
      // Gemini keeps previous turns in the DOM, so without this snapshot the
      // extractor can immediately select the previous answer.
      window.GeminiExtractor.snapshotBeforeTurn(turnId);

      // 2. Switch model if UI supports it
      if (window.GeminiController.switchModelIfAvailable) {
        await window.GeminiController.switchModelIfAvailable(model);
      }

      // 3. Inject and submit prompt (with idle wait and send button polling)
      await window.GeminiController.submitPromptWithRetry(promptText);

      // 4. Stream response for this new turn only
      await streamResponseTurn(turnId, promptText);
    } catch (err) {
      console.error("[Gemini Bridge] Turn execution failed:", err);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: "error",
          turn_id: turnId,
          error: err.message || String(err),
        }));
      }
      if (window.GeminiStatusHUD) window.GeminiStatusHUD.setConnected();
    } finally {
      try { window.postMessage({ source: "webchat2local-content", type: "W2L_CLEAR_ACTIVE_REQUEST" }, "*"); } catch (_) {}
      isGeneratingResponse = false;
      activeTurnId = null;
    }
  }
}

async function streamResponseTurn(turnId, promptSnippet) {
  isGeneratingResponse = true;
  const deadline = Date.now() + TURN_DEADLINE_MS;
  let lastText = "";
  let lastThought = "";
  let targetEl = null;

  // Phase 1: Wait up to 20s for Gemini Web to create the new turn element or start generation
  console.log(`[Gemini Bridge] Waiting for turn ${turnId} to start on Gemini Web...`);
  console.log(`[Gemini Bridge][LOCAL-TRACE] turn_start id=${turnId} prompt_len=${promptSnippet.length}`);

  let turnStarted = false;
  for (let i = 0; i < 200; i++) {
    await sleep(100);

    const domErr = document.querySelector("div[role='alert'], .error-message, [data-test-id*='error'], .toast-error, .banner-error");
    if (domErr && domErr.offsetParent !== null) {
      const errText = (domErr.innerText || "").trim();
      if (/發生錯誤|Something went wrong|error\s*\d+|無法處理/i.test(errText)) {
        throw new Error(`Gemini Web 介面顯示錯誤: ${errText}`);
      }
    }

    targetEl = window.GeminiExtractor.findCurrentTurnResponseElement();
    const generating = window.GeminiController.isGenerating();

    if (i % 20 === 0) console.log(`[Gemini Bridge][LOCAL-TRACE] poll id=${turnId} target=${Boolean(targetEl)} generating=${generating}`);

    if (targetEl || generating) {
      turnStarted = true;
      break;
    }
  }

  if (!turnStarted && !targetEl) {
    throw new Error("Gemini Web 尚未開始生成回應，請確認網頁輸入框是否正常或刷新網頁。");
  }

  // Phase 2: If generation started but container element is still loading, wait for it
  if (!targetEl) {
    for (let i = 0; i < 100; i++) {
      await sleep(100);
      targetEl = window.GeminiExtractor.findCurrentTurnResponseElement();
      if (targetEl) break;
    }
  }

  let idleRounds = 0;
  const maxIdleRounds = 12; // 12 * 80ms = ~1.0 second stabilization debounce

  // Phase 3: Pure DOM-centric streaming directly from the turn's response text box
  while (isGeneratingResponse) {
    if (Date.now() >= deadline) throw new Error(`Gemini response exceeded the ${TURN_DEADLINE_MS / 1000}s browser deadline.`);
    await sleep(80);

    // Network interception already delivered a complete answer to the local
    // server.  Do not wait for the DOM to stabilize or emit a second done.
    if (rawForwarded && !isGeneratingResponse) break;

    if (!targetEl) {
      targetEl = window.GeminiExtractor.findCurrentTurnResponseElement();
    }
    if (!targetEl) {
      continue;
    }

    const state = window.GeminiExtractor.extractCurrentState(targetEl);
    const currentCandidateText = state.text || "";
    const currentCandidateThought = state.thought || "";

    const deltaText = currentCandidateText.slice(lastText.length);
    const deltaThought = currentCandidateThought.slice(lastThought.length);

    if (deltaText.length > 0 || deltaThought.length > 0) {
      console.log(`[Gemini Bridge][LOCAL-TRACE] chunk id=${turnId} text_len=${currentCandidateText.length} delta_len=${deltaText.length}`);
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
      const isGenerating = window.GeminiController.isGenerating();

      // Only count idle if generation has stopped on the page and some output was already received
      if (!isGenerating && (lastText.length > 0 || lastThought.length > 0)) {
        idleRounds++;
        if (idleRounds >= maxIdleRounds) {
          // Finished!
          break;
        }
      }
    }
  }

  if (rawForwarded) {
    console.log(`[Gemini Bridge][LOCAL-TRACE] raw_done id=${turnId}; DOM completion suppressed.`);
    if (window.GeminiStatusHUD) window.GeminiStatusHUD.setConnected();
    return;
  }

  if (lastText.trim().length === 0) {
    console.error(`[Gemini Bridge][LOCAL-TRACE] EMPTY_DONE id=${turnId}`);
    throw new Error("Gemini 完成了要求，但沒有取得任何 assistant 文字；已拒絕送出空 done。");
  }

  // Phase 4: Release locks BEFORE sending done event to eliminate race condition
  isGeneratingResponse = false;
  activeTurnId = null;
  if (ws && ws.readyState === WebSocket.OPEN) {
    console.log(`[Gemini Bridge][LOCAL-TRACE] done_send id=${turnId} text_len=${lastText.length}`);
    ws.send(JSON.stringify({
      type: "done",
      turn_id: turnId,
      text: lastText,
      thought: lastThought,
    }));
  }

  console.log(`[Gemini Bridge] Turn ${turnId} finished (${lastText.length} chars, source=${rawForwarded ? "network" : "dom"}).`);
  if (window.GeminiStatusHUD) window.GeminiStatusHUD.setConnected();
}

/**
 * Extract tool calls from Gemini text response for in-browser MCP Tunnel execution.
 */
function extractInPageToolCalls(text) {
  const tools = [];
  if (!text || typeof text !== "string") return tools;

  // 1. JSON tool_call
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
  if (tools.length > 0) return tools;

  // 2. Direct XML tag fallback
  const standardTools = [
    "execute_command", "run_command", "bash", "terminal",
    "read_file", "write_to_file", "write_file", "edit_file", "list_dir",
    "find_files", "grep_search", "get_workspace_status", "doctor"
  ];
  for (const st of standardTools) {
    const regex = new RegExp(`<${st}(?:\\s+[^>]*)?>([\\s\\S]*?)<\\/${st}>`, "i");
    const m = text.match(regex);
    if (m) {
      const inner = m[1].trim();
      const args = {};
      const paramMatches = [...inner.matchAll(/<([a-zA-Z0-9_-]+)>([\s\S]*?)<\/\1>/g)];
      if (paramMatches.length > 0) {
        for (const pm of paramMatches) {
          args[pm[1].trim()] = pm[2].trim();
        }
      } else if (st === "read_file" || st === "view_file") {
        args.path = inner;
      } else if (st === "execute_command" || st === "run_command" || st === "bash") {
        args.command = inner;
      } else if (st === "list_dir") {
        args.path = inner || ".";
      } else {
        args.content = inner;
      }
      tools.push({ name: st, arguments: args });
      return tools;
    }
  }
  return tools;
}

/**
 * Executes in-page autonomous MCP Tunnel tool loop on Gemini Web.
 */
async function runInPageMcpTunnelLoop(responseEl) {
  if (!responseEl || isGeneratingResponse || activeTurnId) return;
  const state = window.GeminiExtractor ? window.GeminiExtractor.extractCurrentState(responseEl) : null;
  const text = state ? state.text : (responseEl.innerText || "");
  const toolCalls = extractInPageToolCalls(text);

  if (toolCalls.length === 0) return;

  console.log(`[Gemini Tunnel] Detected in-page tool calls:`, toolCalls);
  for (const tc of toolCalls) {
    try {
      if (window.GeminiStatusHUD) {
        window.GeminiStatusHUD.setStatus(`🔧 [Tunnel MCP] 執行 ${tc.name}...`, "#3b82f6");
      }
      const result = await callLocalMcpTool(tc.name, tc.arguments);
      console.log(`[Gemini Tunnel] Tool ${tc.name} result:`, result);

      const resultText = `<tool_result name="${tc.name}">\n${typeof result === "object" ? JSON.stringify(result, null, 2) : String(result)}\n</tool_result>`;
      
      // Settle and inject result into Gemini chat box
      await sleep(500);
      if (window.GeminiController) {
        const editor = window.GeminiController.setInputText(resultText);
        await sleep(300);
        window.GeminiController.clickSendButton(editor);
        if (window.GeminiStatusHUD) {
          window.GeminiStatusHUD.setStatus(`✅ [Tunnel MCP] ${tc.name} 結果已送回 Gemini`, "#10b981");
        }
      }
    } catch (err) {
      console.error(`[Gemini Tunnel] Failed to execute in-page MCP tool ${tc.name}:`, err);
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

