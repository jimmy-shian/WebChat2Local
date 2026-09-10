/**
 * Gemini Web raw transport interceptor.
 * Gemini-only by design: capture the active answer stream so text and
 * <tool_call> payloads survive DOM rendering.
 */
(function () {
  if (window.__WebChat2Local_Interceptor_Loaded) return;
  window.__WebChat2Local_Interceptor_Loaded = true;

  const originalFetch = window.fetch;
  const OriginalXHR = window.XMLHttpRequest;
  let activeRequestId = null;
  let lockedStreamKey = null;
  const processors = new Map();

  window.addEventListener("message", (event) => {
    if (event.source !== window || !event.data) return;
    if (event.data.type === "W2L_SET_ACTIVE_REQUEST") {
      activeRequestId = event.data.request_id;
      lockedStreamKey = null;
      processors.clear();
    } else if (event.data.type === "W2L_CLEAR_ACTIVE_REQUEST") {
      activeRequestId = null;
      lockedStreamKey = null;
      processors.clear();
    } else if (event.data.type === "W2L_PING_INTERCEPTOR") {
      postToContent({ type: "W2L_INTERCEPTOR_PONG", version: "4.0.0-gemini-only" });
    }
  });

  function postToContent(payload) {
    payload.source = "webchat2local-network";
    window.postMessage(payload, "*");
  }

  function isGeminiUrl(url, method) {
    if (String(method || "GET").toUpperCase() !== "POST") return false;
    const lower = String(url || "").toLowerCase();
    // Gemini's August 2026 frontend no longer exposes the old
    // BardFrontendService/StreamGenerate URL. Chat submission is routed through
    // the generic Wiz batchexecute dispatcher with an opaque rpcids value
    // (for example PCck7e in a current anonymous build). Keep the legacy
    // StreamGenerate match for older deployments, but treat batchexecute as the
    // primary transport signal.
    if (!["batchexecute", "streamgenerate", "bardfrontend", "assistant.lamda"].some((p) => lower.includes(p))) return false;
    return !["/sentinel/", "/auth/", "/telemetry", "/gen_title", "/moderation", "/voice", "/transcribe"].some((p) => lower.includes(p));
  }

  function shouldCapture(url) {
    return Boolean(activeRequestId) && (!lockedStreamKey || lockedStreamKey === url);
  }

  function getProcessor(url) {
    let proc = processors.get(url);
    if (proc && proc.isFinished && proc.isFinished()) {
      processors.delete(url);
      proc = null;
    }
    if (!proc) {
      proc = createGeminiProcessor(activeRequestId || "req_" + Date.now(), url);
      processors.set(url, proc);
      if (processors.size > 8) processors.delete(processors.keys().next().value);
    }
    return proc;
  }
  function collectStrings(node, out) {
    if (typeof node === "string") {
      if (!node) return;
      const t = node.trim();
      if (t.startsWith("[") || t.startsWith("{")) {
        try {
          collectStrings(JSON.parse(t), out);
          return;
        } catch (_) {}
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

    function parseTransportFrames(raw) {
      // Gemini/Wiz responses are not guaranteed to be newline-delimited JSON.
      // Depending on the deployment, batchexecute may return either JSON lines
      // or length-prefixed frames. Normalize both into JSON roots before the
      // answer candidate search runs.
      const clean = raw.replace(/^\)\]\}'\s*/, "");
      const roots = [];

      for (const line of clean.split("\n")) {
        const t = line.trim();
        if (!t) continue;
        try {
          roots.push(JSON.parse(t));
          continue;
        } catch (_) {}
      }

      let pos = 0;
      while (pos < clean.length) {
        while (pos < clean.length && /\s/.test(clean[pos])) pos++;
        const start = pos;
        while (pos < clean.length && /\d/.test(clean[pos])) pos++;
        if (start === pos || clean[pos] !== "\n") break;
        const length = Number(clean.slice(start, pos));
        pos++;
        if (!Number.isFinite(length) || length <= 0) break;
        const frame = clean.slice(pos, pos + length);
        if (frame.length < length) break;
        pos += length;
        try {
          roots.push(JSON.parse(frame));
        } catch (_) {}
      }
      return roots;
    }

    function lock() {
      if (!lockedStreamKey) lockedStreamKey = streamKeyVal;
    }

    function emitDone() {
      if (finished) return;
      finished = true;
      // If the only captured text is transport noise (batchexecute plumbing,
      // not the real Gemini answer), unlock the stream key so the next POST
      // can be captured by a fresh processor.
      if (extracted && looksLikeConduitToken(extracted)) {
        postToContent({ type: "done", request_id: reqId, full_text: "" });
        setTimeout(() => { if (lockedStreamKey === streamKeyVal) lockedStreamKey = null; }, 3000);
        return;
      }
      postToContent({ type: "done", request_id: reqId, full_text: extracted });
    }

    // Gemini batchexecute transport may return opaque JSON plumbing that is
    // NOT the assistant answer (e.g. conduit tokens on newer builds).
    function looksLikeConduitToken(s) {
      const t = String(s || "").trim();
      if (/\{[^{}]*"conduit_(?:token|uuid)"[^{}]*\}/i.test(t)) return true;
      if (t.startsWith("{") && (t.includes('"conduit_token"') || t.includes('"conduit_uuid"'))) return true;
      return false;
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

      // 1. Tool calls are highest priority payload. Support streaming tool calls even before </tool_call>
      const toolMatches = clean.match(/<tool_call>[\s\S]*?(?:<\/tool_call>|$)/gi);
      if (toolMatches && toolMatches.length > 0) {
        const latestTool = toolMatches[toolMatches.length - 1].trim();
        if (latestTool.length >= "<tool_call>".length) {
          return latestTool;
        }
      }

      function isPlausibleAnswer(s) {
        if (!s || s.length < 4) return false;
        const trimmed = s.trim();

        // Tool calls are always valid answers
        if (trimmed.startsWith("<tool_call")) return true;

        // Reject pure standalone URLs or protocol-relative URLs
        if (/^(?:https?:)?\/\/\S+$/i.test(trimmed)) return false;
        if (/^\/?\/?(?:www\.)?(?:google\.com|googleusercontent\.com|gstatic\.com)\/\S+$/i.test(trimmed)) return false;

        // Reject Batchexecute RPC identifiers and method tokens (e.g. af.httprm, wrb.fr, f.req, di)
        if (/^[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+$/.test(trimmed)) return false;

        // Reject single-word alphanumeric / hash / opaque tokens (no space, no newline, no CJK)
        if (/^[A-Za-z0-9_.-]{1,64}$/.test(trimmed) && !/[\s\n\u3000\u3400-\u9fff\u3040-\u30ff]/.test(trimmed)) return false;
        if (/^[A-Za-z0-9+/=_-]{16,}$/.test(trimmed) && !/[\s\n\u3000\u3400-\u9fff\u3040-\u30ff]/.test(trimmed)) return false;

        // Reject Google user geolocation / IP footer metadata (e.g. 台灣彰化縣彰化市下廍里, 根據您的 IP 位址, etc.)
        if (/^(?:台灣|臺灣|香港|澳門|日本|美國|中國|Taiwan|Hong Kong|Japan|USA)[\u4e00-\u9fa5A-Za-z0-9\s,.-]{0,35}(?:縣|市|區|里|鄉|鎮|村|路|段|District|City|County|State|Township)$/.test(trimmed)) return false;
        if (/根據您的\s*(?:IP|位置|過去活動)|依據您的位置|Based on your (?:IP|location)|From your IP/i.test(trimmed)) return false;

        // Reject pure JSON punctuation or digits only
        if (/^[\[\]{}",:\s]*$/.test(trimmed)) return false;
        if (/^\d+$/.test(trimmed)) return false;

        // Normal prose or Markdown has spaces, newlines, CJK characters, or markdown syntax
        return /[\s\n\u3000\u3400-\u9fff\u3040-\u30ff]/.test(trimmed) || /[.!?,:;()\[\]{}<>#*_`\-]/.test(trimmed);
      }

      let best = null;
      for (const outer of parseTransportFrames(clean)) {
        const strings = [];
        collectStrings(outer, strings);

        for (const s of strings) {
          if (!isPlausibleAnswer(s)) continue;

          const hasToolCall = s.includes("<tool_call");
          if (hasToolCall) {
            if (!best || !best.includes("<tool_call") || s.length > best.length) {
              best = s;
            }
            continue;
          }

          if (extracted) {
            if (s.startsWith(extracted) && s.length > extracted.length) {
              if (!best || s.length > best.length) best = s;
            } else if (s.length > extracted.length + 15) {
              // Substantially longer candidate found (replace short noise prefix)
              if (!best || s.length > best.length) best = s;
            } else if (!isPlausibleAnswer(extracted)) {
              if (!best || s.length > best.length) best = s;
            }
          } else {
            if (!best || s.length > best.length) best = s;
          }
        }
      }

      return best;
    }

    function findError(raw) {
      if (!raw) return null;
      if (raw.includes("BardErrorInfo") || raw.includes("assistant.boq.bard")) {
        const codeMatch = raw.match(/\[\s*\"type\.googleapis\.com\/assistant\.boq\.bard\.application\.BardErrorInfo\"\s*,\s*(\d+)/i) ||
                          raw.match(/BardErrorInfo[^\d]*(\d{3,5})/i);
        const code = codeMatch ? codeMatch[1] : "1155";
        return `Gemini Web 伺服器傳回錯誤 (BardErrorInfo ${code})：提示詞過長或超過 Web 端單次容量上限。`;
      }
      return null;
    }

    function feed(chunkText) {
      accumulatedRaw += chunkText;
      const err = findError(accumulatedRaw);
      if (err && !finished) {
        finished = true;
        postToContent({ type: "stream_error", request_id: reqId, error: err });
        return;
      }
      const found = findAnswer(accumulatedRaw);
      if (found) {
        // If candidate switched or upgraded
        if (!found.startsWith(extracted)) {
          extracted = "";
        }
        if (found.length > extracted.length) {
          const delta = found.slice(extracted.length);
          extracted = found;
          lock();
          postToContent({ type: "chunk", request_id: reqId, delta, accumulated: extracted });
        }
      }
    }

    return { feed, end: emitDone, isFinished: () => finished };
  }

  window.fetch = async function (...args) {
    let url = "";
    let method = "GET";
    try {
      if (typeof args[0] === "string") {
        url = args[0]; method = (args[1] && args[1].method) || "GET";
      } else if (args[0] && args[0].url) {
        url = args[0].url; method = (args[1] && args[1].method) || args[0].method || "GET";
      }
    } catch (_) {}

    const response = await originalFetch.apply(this, args);
    if (!isGeminiUrl(url, method) || !response?.body || !shouldCapture(url)) return response;

    // Skip clearly binary responses (images, audio, video, protobuf, gzip
    // blobs) so the UTF-8 decoder never turns binary payloads into
    // replacement-character noise that the answer parser mistakes for text.
    const contentType = (() => {
      try { return response.headers.get("content-type") || ""; } catch (_) { return ""; }
    })();
    if (/image\/|audio\/|video\/|application\/octet-stream|application\/x-protobuf|application\/grpc|application\/zip|application\/gzip/i.test(contentType)) {
      return response;
    }

    const rpcids = (() => {
      try { return new URL(url, window.location.href).searchParams.get("rpcids") || ""; } catch (_) { return ""; }
    })();
    postToContent({
      type: "capture_attempt",
      url: String(url).slice(0, 200),
      rpcids,
      transport: String(url).toLowerCase().includes("batchexecute") ? "batchexecute" : "legacy",
      gated: false,
    });
    const proc = getProcessor(url);
    const reader = response.clone().body.getReader();
    const decoder = new TextDecoder("utf-8");
    (async () => {
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          proc.feed(decoder.decode(value, { stream: true }));
        }
        proc.end();
      } catch (e) {
        console.warn("[Gemini Bridge] raw fetch capture failed", e);
        proc.end();
      }
    })();
    return response;
  };

  if (OriginalXHR) {
    function HookedXHR() {
      const xhr = new OriginalXHR();
      let xhrUrl = "";
      let xhrMethod = "GET";
      let lastLen = 0;
      let proc = null;
      const origOpen = xhr.open;
      xhr.open = function (method, url) {
        xhrMethod = String(method || "GET");
        xhrUrl = String(url || "");
        return origOpen.apply(this, arguments);
      };
      xhr.addEventListener("readystatechange", () => {
        if (xhr.readyState < 3 || !isGeminiUrl(xhrUrl, xhrMethod) || !shouldCapture(xhrUrl)) return;
        try {
          if (!proc) proc = getProcessor(xhrUrl);
          const text = xhr.responseText;
          if (typeof text === "string" && text.length > lastLen) {
            proc.feed(text.slice(lastLen));
            lastLen = text.length;
          }
          if (xhr.readyState === 4) proc.end();
        } catch (_) {}
      });
      return xhr;
    }
    HookedXHR.prototype = OriginalXHR.prototype;
    Object.assign(HookedXHR, { UNSENT: 0, OPENED: 1, HEADERS_RECEIVED: 2, LOADING: 3, DONE: 4 });
    window.XMLHttpRequest = HookedXHR;
  }
})();
