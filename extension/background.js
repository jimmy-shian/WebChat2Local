/**
 * Background service worker: automatic cookie sync to the local bridge.
 *
 * Google rotates __Secure-1PSIDTS on its own schedule. Instead of requiring
 * the user to press "Sync cookies" in the popup every time, this worker keeps
 * gemini_cookies.json on the server fresh automatically:
 *
 *   1. chrome.cookies.onChanged -> push immediately whenever Google rotates
 *      __Secure-1PSID / __Secure-1PSIDTS for gemini.google.com.
 *   2. On extension install / browser startup.
 *   3. Every 30 minutes as a safety net (chrome.alarms).
 *
 * The bridge server picks up the refreshed cookie file on the next turn, so
 * the direct (cookie) transport stays alive without manual action.
 */

const BRIDGE_ORIGIN = "http://127.0.0.1:8765";
const COOKIE_URL = "https://gemini.google.com";
const WATCHED_COOKIES = new Set(["__Secure-1PSID", "__Secure-1PSIDTS"]);
const MIN_PUSH_INTERVAL_MS = 5000; // debounce onChanged bursts

let lastPushAt = 0;
let pendingPush = null;

function getCookie(name) {
  return new Promise((resolve) => {
    chrome.cookies.get({ url: COOKIE_URL, name }, (cookie) =>
      resolve(cookie ? cookie.value : "")
    );
  });
}

async function pushCookies(reason) {
  try {
    const onePsid = await getCookie("__Secure-1PSID");
    if (!onePsid) return false; // not logged in yet; nothing to sync
    const onePsidts = await getCookie("__Secure-1PSIDTS");
    const resp = await fetch(BRIDGE_ORIGIN + "/v1/cookies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        "1psid": onePsid,
        "1psidts": onePsidts,
        source: "extension-auto",
        reason,
      }),
    });
    return resp.ok;
  } catch (_) {
    // Server offline; the next trigger will retry.
    return false;
  }
}

function schedulePush(reason) {
  const now = Date.now();
  const elapsed = now - lastPushAt;
  if (elapsed >= MIN_PUSH_INTERVAL_MS) {
    lastPushAt = now;
    pushCookies(reason);
    return;
  }
  if (pendingPush) return;
  pendingPush = setTimeout(() => {
    pendingPush = null;
    lastPushAt = Date.now();
    pushCookies("debounced");
  }, MIN_PUSH_INTERVAL_MS - elapsed);
}

// 1. Google rotated the session cookie -> sync right away.
chrome.cookies.onChanged.addListener((changeInfo) => {
  const cookie = changeInfo.cookie || {};
  const domain = String(cookie.domain || "");
  if (!domain.includes("gemini.google.com")) return;
  if (!WATCHED_COOKIES.has(cookie.name)) return;
  if (changeInfo.removed && !cookie.value) return;
  schedulePush("cookie-change:" + cookie.name);
});

// 2. Install / startup.
chrome.runtime.onInstalled.addListener(() => pushCookies("install"));
chrome.runtime.onStartup.addListener(() => pushCookies("startup"));

// 3. Periodic safety net (also covers missed onChanged events while the
//    service worker was asleep).
chrome.alarms.create("w2l-cookie-sync", { periodInMinutes: 30 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm && alarm.name === "w2l-cookie-sync") pushCookies("periodic");
});