/**
 * PolicyGuard — Content Script
 *
 * Injected into every page. Responsibilities:
 * 1. Reply to GET_HTML requests from the background script
 * 2. Render the in-page floating panel when results arrive
 */

(function () {
  "use strict";

  // Guard against double-injection
  if (window.__policyGuardInjected) return;
  window.__policyGuardInjected = true;

  // ── Message listener ────────────────────────────────────────────────────

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message.type === "GET_HTML") {
      sendResponse({ html: document.documentElement.outerHTML });
      return true;
    }

    if (message.type === "SHOW_PANEL") {
      showPanel(message.result);
      return true;
    }
  });

  // ── In-page floating panel ───────────────────────────────────────────────

  const PANEL_ID = "policyguard-panel";

  function showPanel(result) {
    // Remove existing panel if present
    const existing = document.getElementById(PANEL_ID);
    if (existing) existing.remove();

    const panel = document.createElement("div");
    panel.id = PANEL_ID;
    panel.innerHTML = buildPanelHTML(result);
    applyPanelStyles(panel);

    document.body.appendChild(panel);

    // Close button
    panel.querySelector("#pg-close")?.addEventListener("click", () => panel.remove());

    // Animate in
    requestAnimationFrame(() => {
      panel.style.transform = "translateX(0)";
      panel.style.opacity = "1";
    });

    // Auto-hide after 30 seconds (user can re-open via popup)
    setTimeout(() => {
      if (document.body.contains(panel)) {
        panel.style.opacity = "0";
        panel.style.transform = "translateX(110%)";
        setTimeout(() => panel.remove(), 400);
      }
    }, 30000);
  }

  function getRatingColors(rating) {
    const map = {
      green:  { bg: "#dcfce7", border: "#22c55e", text: "#15803d", badge: "#22c55e" },
      yellow: { bg: "#fef9c3", border: "#f59e0b", text: "#92400e", badge: "#f59e0b" },
      red:    { bg: "#fee2e2", border: "#ef4444", text: "#991b1b", badge: "#ef4444" },
    };
    return map[rating] || { bg: "#f3f4f6", border: "#6b7280", text: "#374151", badge: "#6b7280" };
  }

  function buildPanelHTML(result) {
    const colors = getRatingColors(result.rating);
    const severityEmoji = { high: "🔴", medium: "🟡", low: "🟢" };

    const summaryItems = (result.summaries || [])
      .sort((a, b) => {
        const order = { high: 0, medium: 1, low: 2 };
        return (order[a.severity] ?? 2) - (order[b.severity] ?? 2);
      })
      .map(s => `
        <div class="pg-flag-item">
          <span class="pg-sev-dot">${severityEmoji[s.severity] || "⚪"}</span>
          <span class="pg-flag-text">${escHtml(s.summary)}</span>
        </div>
      `).join("");

    const noFlags = !result.summaries?.length
      ? `<p class="pg-no-flags">✅ No significant risks found.</p>`
      : "";

    return `
      <div class="pg-header" style="background:${colors.border}">
        <div class="pg-logo">🛡️ PolicyGuard</div>
        <button id="pg-close" class="pg-close-btn" title="Close">✕</button>
      </div>
      <div class="pg-body">
        <div class="pg-score-row">
          <div class="pg-score-circle" style="background:${colors.badge}">
            <span class="pg-score-num">${result.score >= 0 ? result.score : "?"}</span>
            <span class="pg-score-label">/100</span>
          </div>
          <div class="pg-verdict">
            <div class="pg-rating-badge" style="color:${colors.badge}">${result.emoji} ${capitalize(result.rating)}</div>
            <div class="pg-verdict-text">${escHtml(result.final_summary || "")}</div>
          </div>
        </div>
        ${summaryItems ? `<div class="pg-flags-section"><div class="pg-flags-title">Risks Detected</div>${summaryItems}</div>` : noFlags}
        <div class="pg-footer">
          <span class="pg-clauses-info">📄 ${result.clauses_found || 0} clauses analyzed · ${result.analysis_time_ms || 0}ms</span>
        </div>
      </div>
    `;
  }

  function applyPanelStyles(panel) {
    Object.assign(panel.style, {
      position: "fixed",
      top: "16px",
      right: "16px",
      width: "340px",
      maxHeight: "80vh",
      overflowY: "auto",
      backgroundColor: "#ffffff",
      borderRadius: "12px",
      boxShadow: "0 20px 60px rgba(0,0,0,0.18), 0 4px 16px rgba(0,0,0,0.10)",
      zIndex: "2147483647",
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      fontSize: "13px",
      color: "#1f2937",
      transition: "transform 0.35s cubic-bezier(0.34,1.56,0.64,1), opacity 0.35s ease",
      transform: "translateX(110%)",
      opacity: "0",
      lineHeight: "1.5",
    });

    // Inject scoped CSS
    if (!document.getElementById("pg-styles")) {
      const style = document.createElement("style");
      style.id = "pg-styles";
      style.textContent = `
        #policyguard-panel .pg-header {
          display: flex; align-items: center; justify-content: space-between;
          padding: 10px 14px; border-radius: 12px 12px 0 0; color: white;
        }
        #policyguard-panel .pg-logo { font-weight: 700; font-size: 14px; }
        #policyguard-panel .pg-close-btn {
          background: none; border: none; color: white; cursor: pointer;
          font-size: 16px; padding: 2px 6px; border-radius: 4px; opacity: 0.8;
        }
        #policyguard-panel .pg-close-btn:hover { opacity: 1; background: rgba(255,255,255,0.2); }
        #policyguard-panel .pg-body { padding: 14px; }
        #policyguard-panel .pg-score-row {
          display: flex; align-items: flex-start; gap: 14px; margin-bottom: 14px;
        }
        #policyguard-panel .pg-score-circle {
          min-width: 60px; height: 60px; border-radius: 50%;
          display: flex; flex-direction: column; align-items: center; justify-content: center;
          color: white; flex-shrink: 0;
        }
        #policyguard-panel .pg-score-num { font-size: 22px; font-weight: 800; line-height: 1; }
        #policyguard-panel .pg-score-label { font-size: 10px; opacity: 0.85; }
        #policyguard-panel .pg-verdict { flex: 1; }
        #policyguard-panel .pg-rating-badge { font-weight: 700; font-size: 15px; margin-bottom: 4px; }
        #policyguard-panel .pg-verdict-text { font-size: 12px; color: #4b5563; line-height: 1.4; }
        #policyguard-panel .pg-flags-section { border-top: 1px solid #f3f4f6; padding-top: 10px; }
        #policyguard-panel .pg-flags-title { font-weight: 600; font-size: 11px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }
        #policyguard-panel .pg-flag-item { display: flex; gap: 8px; align-items: flex-start; margin-bottom: 7px; }
        #policyguard-panel .pg-sev-dot { font-size: 11px; margin-top: 1px; flex-shrink: 0; }
        #policyguard-panel .pg-flag-text { font-size: 12px; color: #374151; line-height: 1.4; }
        #policyguard-panel .pg-no-flags { font-size: 13px; color: #15803d; text-align: center; padding: 8px 0; }
        #policyguard-panel .pg-footer { border-top: 1px solid #f3f4f6; margin-top: 10px; padding-top: 8px; }
        #policyguard-panel .pg-clauses-info { font-size: 11px; color: #9ca3af; }
      `;
      document.head.appendChild(style);
    }
  }

  // ── Utilities ────────────────────────────────────────────────────────────

  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function capitalize(str) {
    return str ? str.charAt(0).toUpperCase() + str.slice(1) : "";
  }

})();
