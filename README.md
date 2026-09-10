# 🛡️ PolicyGuard

> **AI-powered Terms of Service & Privacy Policy risk analyzer — right in your browser.**
> Built with LangGraph, Gemini Flash, FastAPI, and a Chrome MV3 extension.

---

## What It Does

PolicyGuard automatically detects when you're on a ToS or Privacy Policy page, extracts the text, and runs it through a 4-node LangGraph pipeline that produces:

- **A risk score** (0–100) with traffic-light rating 🟢🟡🔴
- **Plain-English summaries** of every red flag found
- **A floating panel** injected directly on the policy page
- **A popup badge** on the extension icon

---

## Architecture

```
Browser Extension (Chrome MV3)
        │  POST /analyze  (page HTML)
        ▼
FastAPI Backend  (localhost:8000)
        │
        ▼
  ┌─────────────────────────── LangGraph Pipeline ───────────────────────────┐
  │                                                                          │
  │  START ──► [extractor_node] ──► (quality check) ──► [risk_flagger_node] │
  │                  ▲                    │ retry ≤2×           │            │
  │                  └────────────────────┘            [summarizer_node]    │
  │                                                            │             │
  │                                              [scorer_node] ──► END      │
  └──────────────────────────────────────────────────────────────────────────┘
```

### Agents

| Agent | LLM? | Role |
|---|---|---|
| **Extractor** | ❌ No | BeautifulSoup — strips boilerplate, isolates policy clauses |
| **Risk-Flagger** | ✅ Hybrid | Regex pre-filter + Gemini Flash for ambiguous clauses |
| **Summarizer** | ✅ Yes | Converts each flag into a plain-English one-liner |
| **Scorer** | ❌ No | Deterministic math → score + traffic-light rating |

### LangGraph State

```python
class PolicyState(TypedDict):
    url: str
    raw_html: str
    clauses: List[str]
    extraction_quality: float   # 0.0–1.0
    extraction_retries: int     # retry counter
    flags: List[dict]
    summaries: List[dict]
    score: int                  # 0–100
    rating: str                 # green | yellow | red
    emoji: str
    final_summary: str
    error: Optional[str]
```

---

## Project Structure

```
policyguard/
├── backend/
│   ├── main.py            # FastAPI app — POST /analyze
│   ├── graph.py           # LangGraph StateGraph (4 nodes + retry edge)
│   ├── prompts.py         # All LLM prompt templates
│   ├── agents/
│   │   ├── extractor.py   # BeautifulSoup HTML parser
│   │   ├── risk_flagger.py # Regex + Gemini hybrid classifier
│   │   ├── summarizer.py  # Plain-English summaries
│   │   └── scorer.py      # Deterministic scoring (0–100)
│   ├── requirements.txt
│   └── .env               # ← Add your GOOGLE_API_KEY here
└── extension/
    ├── manifest.json      # Chrome MV3
    ├── background.js      # Service worker — orchestrates analysis
    ├── content.js         # Injects floating panel into page
    ├── popup/
    │   ├── popup.html
    │   ├── popup.js
    │   └── popup.css
    └── icons/
        ├── icon16.png
        ├── icon48.png
        └── icon128.png
```

---

## Setup

### 1. Get a Free Gemini API Key

1. Go to **[https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)**
2. Click **"Create API Key"**
3. Copy the key

### 2. Configure the Backend

```bash
cd policyguard/backend

# Copy and fill in your API key
# Edit .env and replace: your_gemini_api_key_here
notepad .env
```

Your `.env` should look like:
```
GOOGLE_API_KEY=AIzaSy...your_real_key_here
MODEL_NAME=gemini-1.5-flash
```

### 3. Install Python Dependencies

```bash
cd policyguard/backend
pip install -r requirements.txt
```

### 4. Start the Backend

```bash
python main.py
```

You should see:
```
INFO:     Uvicorn running on http://localhost:8000
```

Test it: open **[http://localhost:8000/health](http://localhost:8000/health)** — should return `{"status":"ok"}`.

### 5. Load the Chrome Extension

1. Open Chrome → go to `chrome://extensions`
2. Enable **Developer mode** (toggle, top-right)
3. Click **"Load unpacked"**
4. Select the `policyguard/extension/` folder
5. The 🛡️ PolicyGuard icon appears in your toolbar

---

## Usage

1. Navigate to any Privacy Policy or Terms of Service page
   - e.g., `reddit.com/help/privacypolicy`, `twitter.com/privacy`, `amazon.com/privacy`
2. PolicyGuard **auto-detects** it and starts analyzing
3. A **floating panel** slides in from the right with the result
4. Click the **extension icon** anytime for the full popup with all flags

You can also click **"Analyze This Page"** in the popup to manually scan any page.

---

## Red Flags Detected

| Category | What It Catches |
|---|---|
| 🔴 **Data Selling** | Selling/renting your data to advertisers or third parties |
| 🔴 **Mandatory Arbitration** | Waiving your right to sue in court |
| 🔴 **Children's Data** | Collecting data from minors, weak age verification |
| 🟡 **Broad Tracking** | Location, behavior, biometrics, device fingerprinting |
| 🟡 **Data Retention** | Indefinite retention, data kept after account deletion |
| 🟡 **Auto-Renewal** | Hard-to-cancel subscriptions, automatic charges |
| 🟡 **ToS Changes** | Terms changed without notice, continued use = consent |
| 🟢 **Government Sharing** | Data shared with law enforcement beyond legal requirements |

---

## Scoring

```
Start: 100 points
  − 22 pts per HIGH severity flag  (max 3 flags counted)
  − 12 pts per MEDIUM severity flag (max 4 flags counted)
  −  4 pts per LOW severity flag    (max 5 flags counted)

Score ≥ 70  →  🟢 Green  (safe to proceed)
Score 40–69 →  🟡 Yellow (read carefully)
Score < 40  →  🔴 Red    (significant risks)
```

---

## API Reference

### `POST /analyze`

**Request:**
```json
{
  "url": "https://example.com/privacy",
  "html_text": "<html>...</html>"
}
```

**Response:**
```json
{
  "url": "https://example.com/privacy",
  "score": 56,
  "rating": "yellow",
  "emoji": "🟡",
  "final_summary": "Caution — this site tracks your behavior broadly and can change terms without notice.",
  "summaries": [
    {
      "category": "BROAD_TRACKING",
      "summary": "This site tracks your location, browsing behavior, and device fingerprint.",
      "severity": "medium"
    }
  ],
  "breakdown": { "high": 0, "medium": 2, "low": 1 },
  "clauses_found": 47,
  "flags_found": 3,
  "analysis_time_ms": 2341
}
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Backend offline (red dot in popup) | Run `python main.py` in `backend/` directory |
| "Could not extract policy text" | Navigate directly to the privacy policy page URL |
| Extension not auto-detecting | Click "Analyze This Page" manually in the popup |
| API key error | Check your `GOOGLE_API_KEY` in `backend/.env` |
| Rate limit error | Gemini free tier: 15 req/min. Wait a moment and retry |
