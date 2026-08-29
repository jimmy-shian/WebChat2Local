/**
 * WebChat2Local - Network Interceptor Unit Test (Node.js, no browser needed)
 *
 * Simulates the MAIN-world environment and verifies that:
 *   1. ChatGPT legacy SSE snapshots are reassembled into pristine text.
 *   2. ChatGPT 2025+ JSON-Patch deltas work, and reasoning/metadata events
 *      are filtered out (no pollution).
 *   3. Gemini batchexecute nested arrays are extracted with XML intact.
 *   4. XML tool tags (<attempt_completion>, <result>, <read_file>) survive.
 *   5. Markdown (tables, code fences) survives byte-for-byte.
 *
 * Run: node tests/test_network_interceptor.js
 */

"use strict";

const assert = require("assert");

/* ------------------------------------------------------------------ *
 *  Mock browser MAIN-world environment
 * ------------------------------------------------------------------ */

const listeners = new Map(); // type -> [fn]

global.window = {
  addEventListener: (type, fn) => {
    if (!listeners.has(type)) listeners.set(type, []);
    listeners.get(type).push(fn);
  },
  postMessage: (msg) => {
    // Deliver ALL posted messages to registered listeners (like a real
    // window message event); consumers filter by source/type themselves.
    const fns = listeners.get("message") || [];
    fns.forEach((fn) => fn({ source: window, data: msg }));
  },
};

// Minimal Request stub so `instanceof Request` works
global.Request = class Request {
  constructor(url, init) {
    this.url = url;
    this.method = (init && init.method) || "GET";
  }
};

// The interceptor captures window.fetch at load time as "originalFetch".
// We pre-define a mock whose behavior is controlled via this variable.
let mockStreamBody = "";
global.window.fetch = async function mockOriginalFetch() {
  return makeStreamResponse(mockStreamBody);
};

function makeStreamResponse(text) {
  const encoder = new TextEncoder();
  let sent = false;
  return {
    body: {
      getReader: () => ({
        read: async () => {
          if (sent) return { value: undefined, done: true };
          sent = true;
          return { value: encoder.encode(text), done: false };
        },
      }),
    },
    clone: function () {
      return makeStreamResponse(text);
    },
  };
}

/* ------------------------------------------------------------------ *
 *  Load the interceptor (it will wrap global.window.fetch)
 * ------------------------------------------------------------------ */

require("../extension/network_interceptor.js");

// The interceptor registered its own "message" listener at load time.
// Keep a reference so createCapture() can reset only the capture listeners.
const interceptorMessageListener = listeners.get("message")[0];

// Helper: content.js side of the protocol
function setActiveRequest(reqId) {
  window.postMessage({ type: "W2L_SET_ACTIVE_REQUEST", request_id: reqId }, "*");
}
function clearActiveRequest() {
  window.postMessage({ type: "W2L_CLEAR_ACTIVE_REQUEST" }, "*");
}

// Capture pipeline: collect chunks/done messages from the interceptor
function createCapture() {
  const cap = { chunks: [], done: null, fullText: "" };
  // Reset ONLY the capture listeners; keep the interceptor's own listener
  // so W2L_SET_ACTIVE_REQUEST / W2L_CLEAR_ACTIVE_REQUEST still reach it.
  listeners.set("message", [interceptorMessageListener]);
  window.addEventListener("message", (event) => {
    if (!event.data || event.data.source !== "webchat2local-network") return;
    if (event.data.type === "chunk") {
      cap.chunks.push(event.data.delta);
      cap.fullText = event.data.accumulated || (cap.fullText + event.data.delta);
    } else if (event.data.type === "done") {
      cap.done = event.data.full_text;
      cap.fullText = event.data.full_text || cap.fullText;
    }
  });
  return cap;
}

/* ------------------------------------------------------------------ *
 *  Test 1: ChatGPT 2025+ JSON-Patch stream (with reasoning noise)
 * ------------------------------------------------------------------ */

async function testChatGPTJsonPatch() {
  console.log("--- Test 1: ChatGPT 2025+ JSON-Patch SSE (reasoning filtered) ---");

  const sseLines = [
    'data: {"v": {"conversation_id": "abc-123", "message": {"status": "in_progress"}}}',
    'data: {"p": "/message/reasoning_content/summary/0", "o": "append", "v": "Thinking about XML tags..."}',
    'data: {"p": "/message/status", "o": "replace", "v": "in_progress"}',
    'data: {"p": "/message/content/parts/0", "o": "append", "v": "<attempt_completion>\\n<result>\\n"}',
    'data: {"p": "/message/content/parts/0", "o": "append", "v": "## 工具列表\\n\\n| 分類 | 名稱 |\\n| --- | --- |\\n| 塔羅 | 偉特塔羅 |\\n\\n"}',
    'data: {"p": "/message/content/parts/0", "o": "append", "v": "```python\\nprint(\'hello\')\\n```\\n"}',
    'data: {"p": "/message/content/parts/0", "o": "append", "v": "</result>\\n<task_progress>\\n- [x] 完成\\n</task_progress>\\n</attempt_completion>"}',
    'data: {"p": "/message/status", "o": "replace", "v": "finished_successfully"}',
    "data: [DONE]",
  ];
  const sseBody = sseLines.join("\n\n") + "\n\n";

  const cap = createCapture();
  setActiveRequest("req_test1");
  mockStreamBody = sseBody;

  await window.fetch("https://chatgpt.com/backend-api/conversation", { method: "POST" });
  await new Promise((r) => setTimeout(r, 50)); // let async reader drain

  clearActiveRequest();

  const expected =
    "<attempt_completion>\n<result>\n" +
    "## 工具列表\n\n| 分類 | 名稱 |\n| --- | --- |\n| 塔羅 | 偉特塔羅 |\n\n" +
    "```python\nprint('hello')\n```\n" +
    "</result>\n<task_progress>\n- [x] 完成\n</task_progress>\n</attempt_completion>";

  assert.ok(cap.done, "done message received");
  assert.strictEqual(cap.fullText, expected, "reassembled text matches pristine source");
  assert.ok(!cap.fullText.includes("Thinking about"), "reasoning content filtered out");
  assert.ok(!cap.fullText.includes("in_progress"), "status metadata filtered out");
  assert.ok(cap.fullText.includes("<attempt_completion>"), "XML opening tag preserved");
  assert.ok(cap.fullText.includes("</attempt_completion>"), "XML closing tag preserved");
  assert.ok(cap.fullText.includes("| 塔羅 | 偉特塔羅 |"), "Markdown table preserved");
  assert.ok(cap.fullText.includes("```python"), "code fence preserved");

  console.log("✅ JSON-Patch stream reassembled 100% pristine (reasoning/metadata filtered)");
}

/* ------------------------------------------------------------------ *
 *  Test 2: ChatGPT legacy snapshot stream
 * ------------------------------------------------------------------ */

async function testChatGPTLegacySnapshot() {
  console.log("--- Test 2: ChatGPT legacy snapshot SSE ---");

  const snap = (text) =>
    `data: ${JSON.stringify({
      message: { content: { parts: [text] }, author: { role: "assistant" } },
      conversation_id: "conv-1",
    })}`;

  const sseBody = [
    snap("Hel"),
    snap("Hello "),
    snap("Hello <read_file>"),
    snap("Hello <read_file><path>index.html</path></read_file>"),
    "data: [DONE]",
  ].join("\n\n");

  const cap = createCapture();
  setActiveRequest("req_test2");
  mockStreamBody = sseBody;

  await window.fetch("https://chatgpt.com/backend-api/conversation", { method: "POST" });
  await new Promise((r) => setTimeout(r, 50));

  clearActiveRequest();

  assert.ok(cap.done, "done received");
  assert.strictEqual(
    cap.fullText,
    "Hello <read_file><path>index.html</path></read_file>",
    "snapshot deltas deduplicated into final text"
  );
  assert.ok(cap.fullText.includes("<read_file>"), "XML tool tag preserved");

  console.log("✅ Legacy snapshot stream deduplicated correctly, XML intact");
}

/* ------------------------------------------------------------------ *
 *  Test 3: Gemini batchexecute stream
 * ------------------------------------------------------------------ */

async function testGeminiBatchexecute() {
  console.log("--- Test 3: Gemini batchexecute nested-array stream ---");

  // Gemini wraps the answer deep inside nested arrays; each chunk carries a
  // progressively longer version of the same text.
  const answer1 = "<attempt_completion>\n<result>\n第一段說明文字，足夠長以通過啟發式過濾器的門檻限制。\n";
  const answer2 = answer1 + "```js\nconst x = 1;\n```\n</result>\n</attempt_completion>";

  const wrap = (text) =>
    JSON.stringify([["wrb.fr", null, JSON.stringify([text]), null, "hash_" + "a".repeat(20)]]) + "\n";

  const rawBody =
    ")]}'\n" +
    "12345\n" +
    wrap(answer1) +
    "\n" +
    "67890\n" +
    wrap(answer2);

  const cap = createCapture();
  setActiveRequest("req_test3");
  mockStreamBody = rawBody;

  await window.fetch(
    "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate",
    { method: "POST" }
  );
  await new Promise((r) => setTimeout(r, 50));

  clearActiveRequest();

  assert.ok(cap.done, "done received");
  assert.strictEqual(cap.fullText, answer2, "Gemini answer extracted verbatim");
  assert.ok(cap.fullText.includes("<attempt_completion>"), "XML preserved");
  assert.ok(cap.fullText.includes("```js"), "code fence preserved");

  console.log("✅ Gemini batchexecute answer extracted verbatim, XML intact");
}

/* ------------------------------------------------------------------ *
 *  Test 4: No armed request -> no capture (stray streams ignored)
 * ------------------------------------------------------------------ */

async function testNoCaptureWhenDisarmed() {
  console.log("--- Test 4: disarmed state ignores streams ---");

  const cap = createCapture();
  // NOTE: no setActiveRequest() call
  mockStreamBody = 'data: {"v":"leak"}\n\ndata: [DONE]\n\n';

  await window.fetch("https://chatgpt.com/backend-api/conversation", { method: "POST" });
  await new Promise((r) => setTimeout(r, 50));

  assert.strictEqual(cap.chunks.length, 0, "no chunks captured while disarmed");
  assert.strictEqual(cap.done, null, "no done captured while disarmed");

  console.log("✅ Disarmed interceptor does not capture stray streams");
}

/* ------------------------------------------------------------------ *
 *  Run all
 * ------------------------------------------------------------------ */

(async () => {
  try {
    await testChatGPTJsonPatch();
    await testChatGPTLegacySnapshot();
    await testGeminiBatchexecute();
    await testNoCaptureWhenDisarmed();
    console.log("\n🎉🎉🎉 全部攔截器測試通過！原始串流文字 100% 保真（XML + Markdown 完整）");
    process.exit(0);
  } catch (err) {
    console.error("\n❌ 測試失敗:", err.message);
    console.error(err.stack);
    process.exit(1);
  }
})();