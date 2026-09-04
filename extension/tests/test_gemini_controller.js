const assert = require("assert");
const GeminiController = require("../extension/gemini_controller.js");

// Minimal DOM Element Mock
class MockElement {
  constructor(tag, attrs = {}, text = "", parent = null) {
    this.tagName = tag.toUpperCase();
    this.attributes = { ...attrs };
    this.innerText = text;
    this.textContent = text;
    this.parentElement = parent;
    this.children = [];
    this.disabled = !!attrs.disabled;
    this.offsetParent = attrs.hidden ? null : {};
    this.clickedCount = 0;
  }

  getAttribute(name) {
    return this.attributes[name] !== undefined ? this.attributes[name] : null;
  }

  setAttribute(name, val) {
    this.attributes[name] = String(val);
  }

  get className() {
    return this.attributes["class"] || "";
  }

  querySelector(sel) {
    for (const child of this.children) {
      if (child.matches(sel)) return child;
      const found = child.querySelector(sel);
      if (found) return found;
    }
    return null;
  }

  querySelectorAll(sel) {
    const list = [];
    for (const child of this.children) {
      if (child.matches(sel)) list.push(child);
      list.push(...child.querySelectorAll(sel));
    }
    return list;
  }

  closest(sel) {
    let curr = this;
    while (curr) {
      if (curr.matches(sel)) return curr;
      curr = curr.parentElement;
    }
    return null;
  }

  matches(sel) {
    const tagMatch = sel.match(/^([a-zA-Z0-9_-]+)/);
    if (tagMatch && this.tagName.toLowerCase() !== tagMatch[1].toLowerCase()) {
      return false;
    }
    if (sel.includes("[aria-label")) {
      const valMatch = sel.match(/\[aria-label(?:\*?=)?['"]?([^'"]+)['"]?\]/);
      if (valMatch && !(this.getAttribute("aria-label") || "").includes(valMatch[1])) return false;
    }
    if (sel.includes("[data-test-id")) {
      if (!this.getAttribute("data-test-id")) return false;
    }
    if (sel.startsWith(".")) {
      const cls = sel.slice(1);
      return this.className.includes(cls);
    }
    return true;
  }

  click() {
    this.clickedCount++;
    if (this.onClick) this.onClick();
  }
}

class MockDocument {
  constructor() {
    this.body = new MockElement("body");
  }

  createElement(tag, attrs = {}, text = "") {
    return new MockElement(tag, attrs, text);
  }

  appendChild(el) {
    el.parentElement = this.body;
    this.body.children.push(el);
  }

  querySelector(sel) {
    return this.body.querySelector(sel);
  }

  querySelectorAll(sel) {
    const all = [];
    const traverse = (node) => {
      for (const child of node.children) {
        if (sel.split(",").some(s => child.matches(s.trim()))) {
          all.push(child);
        }
        traverse(child);
      }
    };
    traverse(this.body);
    return all;
  }
}

async function runTests() {
  console.log("Starting GeminiController Temporary Chat tests...\n");

  // Test 1: Active detected via DOM banner ("這是一段暫時聊天")
  {
    global.window = { location: { href: "https://gemini.google.com/app", hostname: "gemini.google.com" } };
    global.document = new MockDocument();

    const banner = document.createElement("div", { "class": "temporary-chat-header" }, "這是一段暫時聊天。此對話不會儲存。");
    document.appendChild(banner);

    const isTemp = GeminiController.isTemporaryChatActive();
    assert.strictEqual(isTemp, true, "Should detect active temporary chat from Traditional Chinese banner");
    console.log("✓ Test 1 Passed: Banner detection (Traditional Chinese)");
  }

  // Test 2: Active detected via English banner
  {
    global.window = { location: { href: "https://gemini.google.com/app", hostname: "gemini.google.com" } };
    global.document = new MockDocument();

    const banner = document.createElement("div", { "class": "disclaimer" }, "Temporary chats aren't saved in your Gemini Apps activity");
    document.appendChild(banner);

    const isTemp = GeminiController.isTemporaryChatActive();
    assert.strictEqual(isTemp, true, "Should detect active temporary chat from English disclaimer");
    console.log("✓ Test 2 Passed: Banner detection (English)");
  }

  // Test 3: Active detected via "Turn off temporary chat" / "關閉暫時聊天" button
  {
    global.window = { location: { href: "https://gemini.google.com/app", hostname: "gemini.google.com" } };
    global.document = new MockDocument();

    const btn = document.createElement("button", { "aria-label": "關閉暫時聊天", "role": "button" });
    document.appendChild(btn);

    const isTemp = GeminiController.isTemporaryChatActive();
    assert.strictEqual(isTemp, true, "Should detect active temporary chat when 'Turn off' button is present");
    console.log("✓ Test 3 Passed: 'Turn off' button detection");
  }

  // Test 4: Active detected via aria-pressed / class on Temporary chat button
  {
    global.window = { location: { href: "https://gemini.google.com/app", hostname: "gemini.google.com" } };
    global.document = new MockDocument();

    const btn = document.createElement("button", { "aria-label": "Temporary chat", "aria-pressed": "true" });
    document.appendChild(btn);

    const isTemp = GeminiController.isTemporaryChatActive();
    assert.strictEqual(isTemp, true, "Should detect active temporary chat when aria-pressed=true");
    console.log("✓ Test 4 Passed: aria-pressed state detection");
  }

  // Test 5: Inactive when in normal chat
  {
    global.window = { location: { href: "https://gemini.google.com/app", hostname: "gemini.google.com" } };
    global.document = new MockDocument();

    const btn = document.createElement("button", { "aria-label": "Temporary chat", "aria-pressed": "false" });
    document.appendChild(btn);

    const isTemp = GeminiController.isTemporaryChatActive();
    assert.strictEqual(isTemp, false, "Should return false when temporary chat is not active");
    console.log("✓ Test 5 Passed: Inactive normal chat detection");
  }

  // Test 6: ensureTemporaryChat DOES NOT click if already active (Prevent toggle-off bug)
  {
    global.window = { location: { href: "https://gemini.google.com/app", hostname: "gemini.google.com" } };
    global.document = new MockDocument();

    const banner = document.createElement("div", { "class": "temporary-chat-header" }, "這是一段暫時聊天");
    const btn = document.createElement("button", { "aria-label": "關閉暫時聊天" });
    document.appendChild(banner);
    document.appendChild(btn);

    await GeminiController.ensureTemporaryChat();
    assert.strictEqual(btn.clickedCount, 0, "Button MUST NOT be clicked when temporary chat is already active!");
    console.log("✓ Test 6 Passed: Idempotent ensureTemporaryChat did NOT click active button");
  }

  // Test 7: ensureTemporaryChat CLICKS candidate when inactive, then subsequent calls do not click
  {
    global.window = { location: { href: "https://gemini.google.com/app", hostname: "gemini.google.com" } };
    global.document = new MockDocument();

    const btn = document.createElement("button", { "aria-label": "開啟暫時聊天" });
    btn.onClick = () => {
      // Simulate Gemini UI turning on temporary chat
      btn.setAttribute("aria-label", "關閉暫時聊天");
      btn.setAttribute("aria-pressed", "true");
    };
    document.appendChild(btn);

    await GeminiController.ensureTemporaryChat();
    assert.strictEqual(btn.clickedCount, 1, "Candidate button should be clicked once when inactive");
    
    // Call again (Turn 2)
    await GeminiController.ensureTemporaryChat();
    assert.strictEqual(btn.clickedCount, 1, "Candidate button must NOT be clicked again on subsequent turn!");
    console.log("✓ Test 7 Passed: First call turned on, second call kept it open without re-clicking");
  }

  // Test 8: waitForIdleAndReady waits for isGenerating to finish and editor to be ready
  {
    global.window = { location: { href: "https://gemini.google.com/app", hostname: "gemini.google.com" } };
    global.document = new MockDocument();

    const stopBtn = document.createElement("button", { "aria-label": "Stop generating" });
    const editor = document.createElement("div", { "contenteditable": "true", "class": "ql-editor" });
    document.appendChild(stopBtn);
    document.appendChild(editor);

    // Stop button clears after 200ms
    setTimeout(() => {
      stopBtn.attributes["hidden"] = "true";
      stopBtn.offsetParent = null;
    }, 200);

    const readyEditor = await GeminiController.waitForIdleAndReady(2000);
    assert.ok(readyEditor, "Should resolve ready editor after generation stops");
    console.log("✓ Test 8 Passed: waitForIdleAndReady waited for stop button to clear");
  }

  // Test 9: submitPromptWithRetry completes non-blocking text insertion and send button activation
  {
    global.window = { location: { href: "https://gemini.google.com/app", hostname: "gemini.google.com" } };
    global.document = new MockDocument();

    const banner = document.createElement("div", { "class": "temporary-chat-header" }, "這是一段暫時聊天");
    const editor = document.createElement("div", { "contenteditable": "true", "class": "ql-editor" });
    const sendBtn = document.createElement("button", { "aria-label": "Send", "class": "send-button", "disabled": "true" });
    sendBtn.setAttribute("aria-disabled", "true");

    document.appendChild(banner);
    document.appendChild(editor);
    document.appendChild(sendBtn);

    // Simulate Angular enabling the send button after 150ms
    setTimeout(() => {
      sendBtn.disabled = false;
      sendBtn.setAttribute("aria-disabled", "false");
    }, 150);

    await GeminiController.submitPromptWithRetry("Hello from Test 9");
    assert.strictEqual(sendBtn.clickedCount, 1, "Send button should be clicked once enabled");
    console.log("✓ Test 9 Passed: submitPromptWithRetry cleanly waited for send button and submitted");
  }

  console.log("\nAll 9 unit tests passed successfully!");
}

runTests().catch(err => {
  console.error("Test failed:", err);
  process.exit(1);
});

