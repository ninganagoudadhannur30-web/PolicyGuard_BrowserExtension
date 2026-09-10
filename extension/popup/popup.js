/**
 * PolicyGuard — Popup JS
 * Controls popup state transitions and communicates with the background service worker.
 */

"use strict";

// ── DOM refs ─────────────────────────────────────────────────────────────

const states = {
  notPolicy: document.getElementById("state-not-policy"),
  analyzing: document.getElementById("state-analyzing"),
  error:     document.getElementById("state-error"),
  result:    document.getElementById("state-result"),
};

const els = {
  btnAnalyzeNow: document.getElementById("btn-analyze-now"),
  btnRetry:      document.getElementById("btn-retry"),
  btnReanalyze:  document.getElementById("btn-reanalyze"),
  errorMessage:  document.getElementById("error-message"),
  scoreNum:      document.getElementById("score-num"),
  scoreCircle:   document.getElementById("score-circle"),
  ratingText:    document.getElementById("rating-text"),
  finalSummary:  document.getElementById("final-summary"),
  resultHeader:  document.getElementById("result-header"),
  flagsList:     document.getElementById("flags-list"),
  noFlags:       document.getElementById("no-flags"),
  resultMeta:    document.getElementById("result-meta"),
  pillHigh:      document.getElementById("pill-high"),
  pillMedium:    document.getElementById("pill-medium"),
  pillLow:       document.getElementById("pill-low"),
  countHigh:     document.getElementById("count-high"),
  countMedium:   document.getElementById("count-medium"),
  countLow:      document.getElementById("count-low"),
  backendDot:    document.getElementById("backend-dot"),
  backendLabel:  document.getElementById("backend-label"),
  // pipeline steps
  stepExtract:   document.getElementById("step-extract"),
  stepFlag:      document.getElementById("step-flag"),
  stepSummarize: document.getElementById("step-summarize"),
  stepScore:     document.getElementById("step-score"),
};

// ── State machine ─────────────────────────────────────────────────────────

function showState(name) {
  Object.values(states).forEach(el => el.classList.add("hidden"));
  if (states[name]) states[name].classList.remove("hidden");
}

// ── Render result ─────────────────────────────────────────────────────────

const SEVERITY_EMOJI = { high: "🔴", medium: "🟡", low: "🟢" };
const CATEGORY_LABELS = {
  DATA_SELLING:   "Data Selling",
  BROAD_TRACKING: "Broad Tracking",
  ARBITRATION:    "Mandatory Arbitration",
  DATA_RETENTION: "Data Retention",
  AUTO_RENEWAL:   "Auto-Renewal",
  TOS_CHANGE:     "ToS Changes",
  GOV_SHARING:    "Government Sharing",
  CHILDREN_DATA:  "Children's Data",
};

function renderResult(result) {
  // Score circle
  const rating = result.rating || "unknown";
  els.scoreNum.textContent    = result.score >= 0 ? result.score : "?";
  els.scoreCircle.className   = `pg-score-circle ${rating}`;
  els.resultHeader.className  = `pg-result-header ${rating}`;

  // Rating label
  const emoji = result.emoji || "";
  els.ratingText.textContent   = `${emoji} ${capitalize(rating)} Risk`;
  els.ratingText.className     = `pg-rating ${rating}`;
  els.finalSummary.textContent = result.final_summary || "";

  // Breakdown pills
  const bd = result.breakdown || {};
  updatePill(els.pillHigh, els.countHigh, bd.high || 0);
  updatePill(els.pillMedium, els.countMedium, bd.medium || 0);
  updatePill(els.pillLow, els.countLow, bd.low || 0);

  // Flag list
  els.flagsList.innerHTML = "";
  const summaries = (result.summaries || []).sort((a, b) => {
    const o = { high: 0, medium: 1, low: 2 };
    return (o[a.severity] ?? 2) - (o[b.severity] ?? 2);
  });

  if (summaries.length === 0) {
    els.noFlags.classList.remove("hidden");
  } else {
    els.noFlags.classList.add("hidden");
    summaries.forEach(s => {
      const item = document.createElement("div");
      item.className = "pg-flag-item";
      item.innerHTML = `
        <span class="pg-flag-dot">${SEVERITY_EMOJI[s.severity] || "⚪"}</span>
        <div class="pg-flag-content">
          <div class="pg-flag-category">${escHtml(CATEGORY_LABELS[s.category] || s.category)}</div>
          <div class="pg-flag-summary">${escHtml(s.summary)}</div>
        </div>
      `;
      els.flagsList.appendChild(item);
    });
  }

  // Meta
  els.resultMeta.textContent =
    `📄 ${result.clauses_found || 0} clauses · ${result.flags_found || 0} flags · ${result.analysis_time_ms || 0}ms`;

  showState("result");
}

function updatePill(pillEl, countEl, count) {
  if (count > 0) {
    pillEl.classList.remove("hidden");
    countEl.textContent = count;
  } else {
    pillEl.classList.add("hidden");
  }
}

// ── Pipeline animation ────────────────────────────────────────────────────

const PIPELINE_STEPS = ["stepExtract", "stepFlag", "stepSummarize", "stepScore"];
let pipelineTimer = null;
let pipelineStep  = 0;

function startPipelineAnimation() {
  pipelineStep = 0;
  PIPELINE_STEPS.forEach(k => {
    els[k].className = "pg-pipeline-step";
  });
  els[PIPELINE_STEPS[0]].className = "pg-pipeline-step active";

  pipelineTimer = setInterval(() => {
    els[PIPELINE_STEPS[pipelineStep]].className = "pg-pipeline-step done";
    pipelineStep++;
    if (pipelineStep < PIPELINE_STEPS.length) {
      els[PIPELINE_STEPS[pipelineStep]].className = "pg-pipeline-step active";
    } else {
      clearInterval(pipelineTimer);
    }
  }, 1800);
}

function stopPipelineAnimation() {
  if (pipelineTimer) clearInterval(pipelineTimer);
  PIPELINE_STEPS.forEach(k => {
    els[k].className = "pg-pipeline-step done";
  });
}

// ── Backend health check ──────────────────────────────────────────────────

function checkBackend() {
  chrome.runtime.sendMessage({ type: "CHECK_BACKEND" }, (resp) => {
    if (chrome.runtime.lastError) return;
    if (resp?.ok) {
      els.backendDot.className   = "pg-backend-dot online";
      els.backendLabel.textContent = "Backend online";
    } else {
      els.backendDot.className   = "pg-backend-dot offline";
      els.backendLabel.textContent = "Backend offline — run python main.py";
    }
  });
}

// ── Main init ─────────────────────────────────────────────────────────────

async function init() {
  checkBackend();

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) { showState("notPolicy"); return; }

  chrome.runtime.sendMessage({ type: "GET_RESULT", tabId: tab.id }, (resp) => {
    if (chrome.runtime.lastError) { showState("notPolicy"); return; }
    const { status, result } = resp || {};

    switch (status) {
      case "analyzing":
        showState("analyzing");
        startPipelineAnimation();
        break;
      case "done":
        if (result) { renderResult(result); }
        else { showState("notPolicy"); }
        break;
      case "error":
        showState("error");
        els.errorMessage.textContent = result?.error || "Unknown error occurred.";
        break;
      case "not_policy":
      default:
        showState("notPolicy");
        break;
    }
  });

  // Listen for live updates (while popup is open)
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.tabId !== tab.id) return;
    if (msg.type === "STATUS_UPDATE") {
      if (msg.status === "analyzing") {
        showState("analyzing");
        startPipelineAnimation();
      } else if (msg.status === "error") {
        stopPipelineAnimation();
        showState("error");
        els.errorMessage.textContent = msg.error || "Unknown error.";
      }
    }
    if (msg.type === "RESULT_READY") {
      stopPipelineAnimation();
      renderResult(msg.result);
    }
  });
}

// ── Button handlers ───────────────────────────────────────────────────────

els.btnAnalyzeNow.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "ANALYZE_NOW" });
  showState("analyzing");
  startPipelineAnimation();
});

els.btnRetry.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "ANALYZE_NOW" });
  showState("analyzing");
  startPipelineAnimation();
});

els.btnReanalyze.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "ANALYZE_NOW" });
  showState("analyzing");
  startPipelineAnimation();
});

// ── Utilities ─────────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "";
}

// ── Boot ──────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", init);
