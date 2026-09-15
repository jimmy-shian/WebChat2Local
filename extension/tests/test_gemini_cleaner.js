const assert = require("assert");
const GeminiCleaner = require("../gemini_cleaner.js");

// Runs in Node (no window/document/chrome): page-gated APIs must fail safe.
assert.strictEqual(GeminiCleaner.isSupportedPage(), false, "node has no gemini page");
assert.strictEqual(GeminiCleaner.open(), false, "open() outside Gemini must be false");
assert.strictEqual(GeminiCleaner.start(), false, "start() outside Gemini must be false");
assert.strictEqual(GeminiCleaner.start({ total: 10 }), false);

// Message + selector contract with popup.js
assert.strictEqual(GeminiCleaner.MSG_START, "w2l-cleaner-start");
assert.ok(GeminiCleaner.SELECTORS.moreButton.includes("actions-menu-button"));
assert.ok(GeminiCleaner.SELECTORS.deleteMenuButton.includes("delete-button"));
assert.strictEqual(GeminiCleaner.DEFAULT_TOTAL, 120);
assert.strictEqual(GeminiCleaner.DEFAULT_DELAY_MS, 1000);

// Count input parsing (HUD 次數欄位)
assert.strictEqual(GeminiCleaner.parseTotalInput("50", 120), 50);
assert.strictEqual(GeminiCleaner.parseTotalInput("0", 120), 120, "0 falls back");
assert.strictEqual(GeminiCleaner.parseTotalInput("-5", 120), 120, "negative falls back");
assert.strictEqual(GeminiCleaner.parseTotalInput("abc", 120), 120, "nan falls back");
assert.strictEqual(GeminiCleaner.parseTotalInput("", 120), 120, "empty falls back");
assert.strictEqual(GeminiCleaner.parseTotalInput("99999999", 120), 100000, "clamped");

// Initial state is idle
assert.deepStrictEqual(GeminiCleaner.getState(), {
  running: false,
  paused: false,
  count: 0,
  total: 120,
  infinite: false,
  delayMs: 1000,
});

// stop/close are safe no-ops without a HUD
GeminiCleaner.stop();
GeminiCleaner.close();
assert.strictEqual(GeminiCleaner.getState().running, false);

// Delay input parsing (HUD 間隔欄位, ms, clamp 200~5000)
assert.strictEqual(GeminiCleaner.parseDelayInput("400", 1000), 400);
assert.strictEqual(GeminiCleaner.parseDelayInput("50", 1000), 200, "clamped to min");
assert.strictEqual(GeminiCleaner.parseDelayInput("99999", 1000), 5000, "clamped to max");
assert.strictEqual(GeminiCleaner.parseDelayInput("abc", 1000), 1000, "nan falls back");

console.log("test_gemini_cleaner: all assertions passed");
