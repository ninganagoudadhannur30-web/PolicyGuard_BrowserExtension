/**
 * PolicyGuard — Background Service Worker
 *
 * Responsibilities:
 * 1. Detect when the user navigates to a page that likely contains a Privacy Policy / ToS
 * 2. Trigger content script to extract page HTML
 * 3. Call the PolicyGuard FastAPI backend
 * 4. Store result and update badge icon
 * 5. Relay results to popup on demand
 */

const BACKEND_URL = "http://localhost:8000";
const POLICY_URL_PATTERN = /privacy|terms|tos|legal|cookies|gdpr|conditions|agreement|datenschutz|politique/i;
const POLICY_TITLE_PATTERN = /privacy|terms of service|terms and conditions|cookie|legal|tos/i;

// In-memory store: tabId → analysis result
const tabResults = new Map();
const tabStatus = new Map(); // 'idle' | 'analyzing' | 'done' | 'error' | 'not_policy'

// ── Badge helpers ──────────────────────────────────────────────────────────

const BADGE_CONFIG = {
  green:   { text: "✓",  color: "#22c55e" },
  yellow:  { text: "!",  color: "#f59e0b" },
  red:     { text: "✕",  color: "#ef4444" },
  unknown: { text: "?",  color: "#6b7280" },
  loading: { text: "…",  color: "#3b82f6" },
};

function setBadge(tabId, type) {
  const cfg = BADGE_CONFIG[type] || BADGE_CONFIG.unknown;
  chrome.action.setBadgeText({ tabId, text: cfg.text });
  chrome.action.setBadgeBackgroundColor({ tabId, color: cfg.color });
}

function clearBadge(tabId) {
  chrome.action.setBadgeText({ tabId, text: "" });
}

// ── Policy page detection ──────────────────────────────────────────────────

function isPolicyPage(url, title) {
  if (!url) return false;
  try {
    const parsed = new URL(url);
    const path = parsed.pathname + parsed.search;
    if (POLICY_URL_PATTERN.test(path)) return true;
    if (POLICY_URL_PATTERN.test(parsed.hostname)) return true;
  } catch (_) {}
  if (title && POLICY_TITLE_PATTERN.test(title)) return true;
  return false;
}

// ── Core analysis flow ─────────────────────────────────────────────────────

async function analyzeTab(tabId, url) {
  tabStatus.set(tabId, "analyzing");
  setBadge(tabId, "loading");

  // Notify popup if open
  chrome.runtime.sendMessage({ type: "STATUS_UPDATE", tabId, status: "analyzing" }).catch(() => {});

  try {
    // Ask content script for the page HTML
    let response;
    try {
      response = await chrome.tabs.sendMessage(tabId, { type: "GET_HTML" });
    } catch (err) {
      console.warn("PolicyGuard: content script not ready, injecting...");
      await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
      await new Promise(r => setTimeout(r, 300));
      response = await chrome.tabs.sendMessage(tabId, { type: "GET_HTML" });
    }

    if (!response?.html || response.html.length < 200) {
      throw new Error("Page HTML too short or unavailable");
    }

    // Call backend
    const apiResponse = await fetch(`${BACKEND_URL}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, html_text: response.html }),
    });

    if (!apiResponse.ok) {
      const errorData = await apiResponse.json().catch(() => ({}));
      throw new Error(errorData.detail || `Backend returned ${apiResponse.status}`);
    }

    const result = await apiResponse.json();

    tabResults.set(tabId, { ...result, timestamp: Date.now() });
    tabStatus.set(tabId, "done");
    setBadge(tabId, result.rating || "unknown");

    // Notify popup
    chrome.runtime.sendMessage({ type: "RESULT_READY", tabId, result }).catch(() => {});

    // Notify content script to show in-page panel
    chrome.tabs.sendMessage(tabId, { type: "SHOW_PANEL", result }).catch(() => {});

  } catch (err) {
    console.error("PolicyGuard analysis error:", err);
    tabStatus.set(tabId, "error");
    tabResults.set(tabId, { error: err.message, timestamp: Date.now() });
    setBadge(tabId, "unknown");

    chrome.runtime.sendMessage({
      type: "STATUS_UPDATE", tabId, status: "error", error: err.message
    }).catch(() => {});
  }
}

// ── Tab lifecycle listeners ────────────────────────────────────────────────

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete") return;
  const url = tab.url || "";
  const title = tab.title || "";

  // Skip extension pages, chrome:// pages, etc.
  if (!url.startsWith("http")) {
    clearBadge(tabId);
    tabStatus.set(tabId, "not_policy");
    return;
  }

  if (isPolicyPage(url, title)) {
    console.log(`PolicyGuard: policy page detected — ${url}`);
    analyzeTab(tabId, url);
  } else {
    clearBadge(tabId);
    tabStatus.set(tabId, "not_policy");
    tabResults.delete(tabId);
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  tabResults.delete(tabId);
  tabStatus.delete(tabId);
});

// ── Message handler (from popup or content script) ────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const { type } = message;

  if (type === "GET_RESULT") {
    const { tabId } = message;
    sendResponse({
      status: tabStatus.get(tabId) || "idle",
      result: tabResults.get(tabId) || null,
    });
    return true;
  }

  if (type === "ANALYZE_NOW") {
    chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
      if (tab) {
        analyzeTab(tab.id, tab.url);
        sendResponse({ started: true });
      }
    });
    return true; // async
  }

  if (type === "CHECK_BACKEND") {
    fetch(`${BACKEND_URL}/health`)
      .then(r => r.json())
      .then(data => sendResponse({ ok: true, data }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }
});
