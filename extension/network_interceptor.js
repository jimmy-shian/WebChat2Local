/**
 * WebChat2Local Network Interceptor (v3.3.0 - Raw Transport Capture)
 * Injected into MAIN world at document_start (see manifest.json).
 *
 * Purpose:
 *   Captures the RAW, UNRENDERED network stream (SSE / Batchexecute) directly from
 *   ChatGPT, Gemini & DeepSeek backends. This is the ONLY reliable way to obtain pristine text
 *   containing XML tool tags (<attempt_completion>, <read_file>, <result> ...),
 *   because once the browser renders the response into DOM, those tags are consumed
 *   as HTML elements and can never be recovered from innerText.
 *
 * Supported transports:
 *   - ChatGPT:  POST backend-api conversation endpoints (classic SSE "data: {...}"
 *               lines, including the 2025+ JSON-Patch {"p","o","v"} delta format)
 *   - Gemini:   POST StreamGenerate / Batchexecute (nested JSON arrays)
 *   - DeepSeek: POST /api/v0/chat/completion endpoints (OpenAI-like SSE streams)
 *
 * Communication:
 *   - content.js -> interceptor : window.postMessage({type:"W2L_SET_ACTIVE_REQUEST", request_id})
 *                                 window.postMessage({type:"W2L_CLEAR_ACTIVE_REQUEST"})
 *   - interceptor -> content.js : window.postMessage({source:"webchat2local-network", ...})
 */

(function () {
  if (window.__WebChat2Local_Interceptor_Loaded) return;
  window.__WebChat2Local_Interceptor_Loaded = true;

  console.log("[WebChat2Local Interceptor v3.3.0] Hooking fetch + XHR in MAIN world at document_start.");

  const originalFetch = window.fetch;
  const OriginalXHR = window.XMLHttpRequest; // may be undefined in non-browser test envs

  let activeRequestId = null;
  let lockedStreamKey = null; // once a stream yields text, only that stream may emit

  window.addEventListener("message", (event) => {
    if (event.source !== window || !event.data) return;
    if (event.data.type === "W2L_SET_ACTIVE_REQUEST") {
      activeRequestId = event.data.request_id;
      lockedStreamKey = null;
      processors.clear(); // new request: discard finished processors (URLs repeat across requests)
      console.log("[WebChat2Local Interceptor] Active request set to:", activeRequestId);
    } else if (event.data.type === "W2L_CLEAR_ACTIVE_REQUEST") {
      activeRequestId = null;
      lockedStreamKey = null;
      processors.clear();
    } else if (event.data.type === "W2L_PING_INTERCEPTOR") {
      // Version handshake so the server logs can verify which interceptor
      // version is actually loaded in the page.
      postToContent({ type: "W2L_INTERCEPTOR_PONG", version: "3.3.0" });
    }
  });

  function postToContent(payload) {
    payload.source = "webchat2local-network";
    try {
      window.postMessage(payload, "*");
    } catch (e) {
      console.warn("[WebChat2Local Interceptor] postMessage failed:", e);
    }
  }

  /* ------------------------------------------------------------------ *
   *  URL classification
   * ------------------------------------------------------------------ */

  // Noise filters: requests that stream text but are NOT the main answer.
  const NOISE_PATTERNS = [
    "/sentinel/", "/auth/", "/lat/", "/telemetry", "/gen_title",
    "conversation_title", "/attribution", "/moderation", "score_stream",
    "/react_compile", "/voice", "/transcribe", "/register", "/onboarding",
  ];

  function classifyUrl(url, method) {
    if (!url || String(method || "GET").toUpperCase() !== "POST") return null;
    const lower = String(url).toLowerCase();
    if (NOISE_PATTERNS.some((p) => lower.includes(p))) return null;

    const isChatGPT =
      (lower.includes("chatgpt.com") || lower.includes("openai.com")) &&
      (lower.includes("/conversation") ||
        lower.includes("/backend-anon/") ||
        lower.includes("/backend-api/"));

    if (isChatGPT) return "chatgpt";

    const isDeepSeek =
      lower.includes("deepseek.com") &&
      (lower.includes("/chat") || lower.includes("/completion") || lower.includes("/api/v0/"));

    if (isDeepSeek) return "deepseek";

    const isGemini =
      lower.includes("streamgenerate") ||
      lower.includes("batchexecute") ||
      lower.includes("bardfrontend") ||
      lower.includes("assistant.lamda");

    if (isGemini) return "gemini";

    return null;
  }

  /* ------------------------------------------------------------------ *
   *  ChatGPT stream processor (SSE)
   * ------------------------------------------------------------------ */

  function createChatGPTProcessor(reqId, streamKeyVal) {
    let buffer = "";
    let accumulated = "";
    let finished = false;

    function lock() {
      if (!lockedStreamKey) lockedStreamKey = streamKeyVal;
    }

    function emitDone() {
      if (finished) return;
      finished = true;
      if (accumulated.length > 0) {
        postToContent({ type: "done", request_id: reqId, full_text: accumulated });
      }
    }

    function handlePiece(text, isSnapshot) {
      if (!text) return;
      lock();

      if (isSnapshot) {
        // Full snapshot of the message so far -> emit only the new suffix.
        if (text.length > accumulated.length) {
          const delta = text.slice(accumulated.length);
          accumulated = text;
          postToContent({ type: "chunk", request_id: reqId, delta, accumulated });
        }
      } else {
        accumulated += text;
        postToContent({ type: "chunk", request_id: reqId, delta: text, accumulated });
      }
    }

    /**
     * Extracts { text, isSnapshot } from one SSE JSON payload, or null.
     *
     * 2025+ JSON-Patch format:
     *   {"p": "/message/content/parts/0", "o": "append",  "v": "delta text"}  -> delta
     *   {"p": "/message/content/parts/0", "o": "replace", "v": "full so far"} -> snapshot
     *   {"p": "/message/reasoning_content/...", ...}                          -> SKIP (reasoning)
     *   {"p": "/message/status" | "/conversation_id" | ..., ...}              -> SKIP (metadata)
     *
     * Legacy snapshot format:
     *   {"message": {"content": {"parts": ["..."]}}}                          -> snapshot
     *   {"v": {"message": {...}}}                                             -> snapshot (wrapped)
     */
    function extract(parsed) {
      if (!parsed || typeof parsed !== "object") return null;

      const p = typeof parsed.p === "string" ? parsed.p : null;

      if (p) {
        // Only accept assistant answer content; everything else is noise.
        if (!p.includes("/content/parts")) return null;
        if (typeof parsed.v === "string") {
          return { text: parsed.v, isSnapshot: parsed.o === "replace" };
        }
        return null;
      }

      // Legacy full-snapshot
      const c = parsed.message && parsed.message.content;
      if (c) {
        if (Array.isArray(c.parts)) {
          return {
            text: c.parts.filter((x) => typeof x === "string").join(""),
            isSnapshot: true,
          };
        }
        if (typeof c.text === "string") {
          return { text: c.text, isSnapshot: true };
        }
        return null;
      }

      // Wrapped snapshot: {"v": {"message": {...}}}
      if (parsed.v && typeof parsed.v === "object") {
        return extract(parsed.v);
      }

      // Bare delta: {"v": "..."}
      if (typeof parsed.v === "string") {
        return { text: parsed.v, isSnapshot: false };
      }

      // Generic fallbacks
      if (parsed.delta && typeof parsed.delta.content === "string") {
        return { text: parsed.delta.content, isSnapshot: false };
      }
      if (parsed.delta && typeof parsed.delta.text === "string") {
        return { text: parsed.delta.text, isSnapshot: false };
      }

      return null;
    }

    function feed(chunkText) {
      buffer += chunkText;
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;

        const dataStr = trimmed.slice(5).trim();
        if (!dataStr) continue;

        if (dataStr === "[DONE]") {
          emitDone();
          return;
        }

        try {
          const parsed = JSON.parse(dataStr);
          const piece = extract(parsed);
          if (piece) handlePiece(piece.text, piece.isSnapshot);
        } catch (e) {
          // Keep-alive comments / non-JSON lines - ignore.
        }
      }
    }

    return { feed, end: emitDone };
  }

  /* ------------------------------------------------------------------ *
   *  Gemini stream processor (Batchexecute / StreamGenerate)
   * ------------------------------------------------------------------ */

  function collectStrings(node, out) {
    if (typeof node === "string") {
      if (node.length === 0) return;
      // Gemini double-encodes payloads: a string may itself contain JSON
      // (e.g. the wrb.fr element holds '["answer text"]'). Recurse into it.
      const t = node.trim();
      if (t.startsWith("[") || t.startsWith("{")) {
        try {
          collectStrings(JSON.parse(t), out);
          return;
        } catch (e) {
          // Not valid JSON - treat as a plain string below.
        }
      }
      out.push(node);
      return;
    }
    if (Array.isArray(node)) {
      for (const item of node) collectStrings(item, out);
    } else if (node && typeof node === "object") {
      for (const key of Object.keys(node)) collectStrings(node[key], out);
    }
  }

  function createGeminiProcessor(reqId, streamKeyVal) {
    let accumulatedRaw = "";
    let extracted = "";
    let finished = false;

    function lock() {
      if (!lockedStreamKey) lockedStreamKey = streamKeyVal;
    }

    function emitDone() {
      if (finished) return;
      finished = true;
      if (extracted.length > 0) {
        postToContent({ type: "done", request_id: reqId, full_text: extracted });
      }
    }

    /**
     * Finds the model's answer inside the accumulated raw batchexecute payload.
     * Strategy: the answer is a string that grows monotonically across chunks.
     *   - Once we have `extracted`, only accept strings that START WITH it and
     *     are longer (guarantees we always extend the same answer).
     *   - For the first pick, choose the longest plausible markdown string,
     *     skipping ids / hashes / numbers.
     */
    function findAnswer(raw) {
      const clean = raw.replace(/^\)\]\}'\s*/, "");
      let best = null;

      for (const line of clean.split("\n")) {
        const t = line.trim();
        if (!t.startsWith("[")) continue;

        let outer;
        try {
          outer = JSON.parse(t);
        } catch (e) {
          continue; // partial line - more data will arrive
        }

        const strings = [];
        collectStrings(outer, strings);

        for (const s of strings) {
          if (extracted) {
            if (s.startsWith(extracted) && s.length > extracted.length) {
              if (!best || s.length > best.length) best = s;
            }
          } else {
            if (
              s.length > 40 &&
              !/^[a-f0-9\-_]{8,}$/i.test(s) &&
              !/^\d+$/.test(s) &&
              !/^[\[\]{}",:\s]*$/.test(s)
            ) {
              if (!best || s.length > best.length) best = s;
            }
          }
        }
      }
      return best;
    }

    function feed(chunkText) {
      accumulatedRaw += chunkText;
      const found = findAnswer(accumulatedRaw);
      if (found && found.length > extracted.length) {
        const delta = found.slice(extracted.length);
        extracted = found;
        lock();
        postToContent({ type: "chunk", request_id: reqId, delta, accumulated: extracted });
      }
    }

    return { feed, end: emitDone };
  }

  /* ------------------------------------------------------------------ *
   *  DeepSeek stream processor (SSE)
   * ------------------------------------------------------------------ */

  function createDeepSeekProcessor(reqId, streamKeyVal) {
    let buffer = "";
    let accumulated = "";
    let finished = false;

    function lock() {
      if (!lockedStreamKey) lockedStreamKey = streamKeyVal;
    }

    function emitDone() {
      if (finished) return;
      finished = true;
      if (accumulated.length > 0) {
        postToContent({ type: "done", request_id: reqId, full_text: accumulated });
      }
    }

    function handlePiece(text, isSnapshot) {
      if (!text) return;
      lock();

      if (isSnapshot) {
        if (text.length > accumulated.length) {
          const delta = text.slice(accumulated.length);
          accumulated = text;
          postToContent({ type: "chunk", request_id: reqId, delta, accumulated });
        }
      } else {
        accumulated += text;
        postToContent({ type: "chunk", request_id: reqId, delta: text, accumulated });
      }
    }

    function extract(parsed) {
      if (!parsed || typeof parsed !== "object") return null;

      // 1. Standard OpenAI choices format (used by DeepSeek Web API)
      if (Array.isArray(parsed.choices) && parsed.choices.length > 0) {
        const choice = parsed.choices[0];
        if (choice.delta) {
          // If reasoning_content exists, skip it to avoid breaking agent tools
          if (typeof choice.delta.content === "string") {
            return { text: choice.delta.content, isSnapshot: false };
          }
          if (typeof choice.delta.text === "string") {
            return { text: choice.delta.text, isSnapshot: false };
          }
        }
        if (typeof choice.text === "string") {
          return { text: choice.text, isSnapshot: false };
        }
      }

      // 2. Direct string properties
      if (typeof parsed.content === "string") {
        return { text: parsed.content, isSnapshot: false };
      }
      if (typeof parsed.delta === "string") {
        return { text: parsed.delta, isSnapshot: false };
      }
      if (typeof parsed.v === "string") {
        return { text: parsed.v, isSnapshot: false };
      }

      return null;
    }

    function feed(chunkText) {
      buffer += chunkText;
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;

        const dataStr = trimmed.slice(5).trim();
        if (!dataStr) continue;

        if (dataStr === "[DONE]") {
          emitDone();
          return;
        }

        try {
          const parsed = JSON.parse(dataStr);
          const piece = extract(parsed);
          if (piece) handlePiece(piece.text, piece.isSnapshot);
          if (parsed.choices && parsed.choices[0] && parsed.choices[0].finish_reason === "stop") {
            emitDone();
            return;
          }
        } catch (e) {}
      }
    }

    return { feed, end: emitDone };
  }

  /* ------------------------------------------------------------------ *
   *  Processor registry + capture gating
   * ------------------------------------------------------------------ */

  const processors = new Map(); // streamKey -> processor

  function getProcessor(kind, url) {
    let proc = processors.get(url);
    if (proc) return proc;

    const reqId = activeRequestId || "req_" + Date.now();
    if (kind === "gemini") {
      proc = createGeminiProcessor(reqId, url);
    } else if (kind === "deepseek") {
      proc = createDeepSeekProcessor(reqId, url);
    } else {
      proc = createChatGPTProcessor(reqId, url);
    }
    processors.set(url, proc);

    // Simple GC: keep at most 8 recent streams.
    if (processors.size > 8) {
      const oldest = processors.keys().next().value;
      processors.delete(oldest);
    }
    return proc;
  }

  function shouldCapture(url) {
    if (!activeRequestId) return false;               // no armed request -> don't capture
    if (lockedStreamKey && lockedStreamKey !== url) return false; // locked to another stream
    return true;
  }

  /* ------------------------------------------------------------------ *
   *  fetch hook
   * ------------------------------------------------------------------ */

  window.fetch = async function (...args) {
    let url = "";
    let method = "GET";
    try {
      if (typeof args[0] === "string") {
        url = args[0];
        method = (args[1] && args[1].method) || "GET";
      } else if (args[0] instanceof Request) {
        url = args[0].url;
        method = args[0].method || "GET";
      } else if (args[0] && args[0].url) {
        url = args[0].url;
        method = (args[1] && args[1].method) || args[0].method || "GET";
      }
    } catch (e) {}

    const response = await originalFetch.apply(this, args);

    try {
      const kind = classifyUrl(url, method);
      if (kind && response && response.body) {
        // Diagnostic: report every matching URL so the server log reveals
        // whether the hook fires and whether gating blocked the capture.
        postToContent({ type: "capture_attempt", url: String(url).slice(0, 200), gated: !shouldCapture(url) });
      }
      if (kind && response && response.body && shouldCapture(url)) {
        console.log("[WebChat2Local Interceptor] Capturing raw fetch stream:", String(url).slice(0, 120));
        const proc = getProcessor(kind, url);
        const clone = response.clone();
        const reader = clone.body.getReader();
        const decoder = new TextDecoder("utf-8");

        (async () => {
          try {
            while (true) {
              const { value, done } = await reader.read();
              if (done) break;
              proc.feed(decoder.decode(value, { stream: true }));
            }
            proc.end();
          } catch (err) {
            console.error("[WebChat2Local Interceptor] fetch stream read error:", err);
            proc.end();
          }
        })();
      }
    } catch (e) {
      console.warn("[WebChat2Local Interceptor] fetch hook error:", e);
    }

    return response;
  };

  /* ------------------------------------------------------------------ *
   *  XMLHttpRequest hook (fallback transport)
   * ------------------------------------------------------------------ */

  function HookedXHR() {
    const xhr = new OriginalXHR();
    let xhrUrl = "";
    let xhrMethod = "GET";
    let lastLen = 0;
    let proc = null;

    const origOpen = xhr.open;
    xhr.open = function (method, u) {
      xhrMethod = String(method || "GET");
      xhrUrl = String(u || "");
      return origOpen.apply(this, arguments);
    };

    xhr.addEventListener("readystatechange", () => {
      try {
        if (xhr.readyState < 3) return;
        const kind = classifyUrl(xhrUrl, xhrMethod);
        if (!kind || !shouldCapture(xhrUrl)) return;
        if (!proc) proc = getProcessor(kind, xhrUrl);

        const text = xhr.responseText;
        if (typeof text !== "string") return;

        if (text.length > lastLen) {
          proc.feed(text.slice(lastLen));
          lastLen = text.length;
        }
        if (xhr.readyState === 4) proc.end();
      } catch (e) {
        // responseText unavailable for non-text responseType - ignore.
      }
    });

    return xhr;
  }

  if (OriginalXHR) {
    HookedXHR.prototype = OriginalXHR.prototype;
    Object.assign(HookedXHR, {
      UNSENT: 0,
      OPENED: 1,
      HEADERS_RECEIVED: 2,
      LOADING: 3,
      DONE: 4,
    });
    window.XMLHttpRequest = HookedXHR;
  }

  /* ------------------------------------------------------------------ *
   *  WebSocket hook (some ChatGPT builds stream over a duplex WS)
   * ------------------------------------------------------------------ */

  const OriginalWS = window.WebSocket;
  if (OriginalWS) {
    window.WebSocket = function (...args) {
      const ws = new OriginalWS(...args);
      const wsUrl = String(args[0] || "");
      let wsProc = null;

      ws.addEventListener("message", (e) => {
        try {
          if (typeof e.data !== "string") return;
          if (!activeRequestId) return;

          if (!wsProc) {
            const key = "ws:" + wsUrl;
            if (lockedStreamKey && lockedStreamKey !== key) return;
            wsProc = createChatGPTProcessor(activeRequestId, key);
          }

          // WS frames are raw JSON (not SSE "data:" lines) - normalize each
          // line into a synthetic SSE frame so the shared parser can be reused.
          const frames = e.data.split("\n");
          for (const f of frames) {
            const t = f.trim();
            if (!t) continue;
            const payload = t.startsWith("data:") ? t.slice(5).trim() : t;
            if (!payload || payload === "[DONE]") continue;
            try {
              wsProc.feed("data: " + JSON.stringify(JSON.parse(payload)) + "\n");
            } catch (err) {}
          }
        } catch (err) {}
      });

      return ws;
    };
    window.WebSocket.prototype = OriginalWS.prototype;
    Object.assign(window.WebSocket, {
      CONNECTING: OriginalWS.CONNECTING,
      OPEN: OriginalWS.OPEN,
      CLOSING: OriginalWS.CLOSING,
      CLOSED: OriginalWS.CLOSED,
    });
  }
})();
