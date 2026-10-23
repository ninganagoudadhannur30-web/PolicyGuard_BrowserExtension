# 🛡️ PolicyGuard

> **A Chrome extension that spots risky clauses in Terms of Service and Privacy Policy pages and explains them in plain English.**
> Built with LangGraph, Gemini Flash, FastAPI, and a Chrome MV3 extension.

> **Learning project.** PolicyGuard is not legal advice, and its results are heuristic. Built with AI assistance: I directed the design and am studying each component.

---

## What it does

PolicyGuard detects when you are on a Terms of Service or Privacy Policy page, extracts the text, and runs it through a 4-node LangGraph pipeline that produces:

- **A risk score** (0 to 100) with a green, yellow, or red rating
- **Plain-English summaries** of every flag found
- **A floating panel** injected directly on the policy page
- **A popup badge** on the extension icon

## How it works, in short

1. The extension sends the page's HTML to a local FastAPI backend.
2. **Extractor (no LLM):** BeautifulSoup strips navigation and boilerplate and isolates the policy clauses. If the extraction looks poor, the step is retried up to two times.
3. **Risk-flagger (hybrid):** a regex pre-filter catches clear patterns cheaply, and Gemini Flash classifies only the ambiguous clauses.
4. **Summarizer (LLM):** turns each flag into a one-line plain-English summary.
5. **Scorer (no LLM):** a deterministic formula turns the flags into a score and a rating, so the same flags always give the same score.

Keeping the extraction and scoring steps free of an LLM makes the pipeline cheaper, faster, and easier to test.

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
| **Extractor** | No | BeautifulSoup: strips boilerplate, isolates policy clauses |
| **Risk-Flagger** | Hybrid | Regex pre-filter, then Gemini Flash for ambiguous clauses |
| **Summarizer** | Yes | Converts each flag into a plain-English one-liner |
| **Scorer** | No | Deterministic math: score and rating |

### LangGraph state

```python
class PolicyState(TypedDict):
    url: str
    raw_html: str
    clauses: List[str]
    extraction_quality: float   # 0.0 to 1.0
    extraction_retries: int     # retry counter
    flags: List[dict]
    summaries: List[dict]
    score: int                  # 0 to 100
    rating: str                 # green | yellow | red
    emoji: str
    final_summary: str
    error: Optional[str]
```

---

## Project structure

```
policyguard/
├── backend/
│   ├── main.py             # FastAPI app: POST /analyze
│   ├── graph.py            # LangGraph StateGraph (4 nodes + retry edge)
│   ├── prompts.py          # All LLM prompt templates
│   ├── agents/
│   │   ├── extractor.py    # BeautifulSoup HTML parser
│   │   ├── risk_flagger.py # Regex + Gemini hybrid classifier
│   │   ├── summarizer.py   # Plain-English summaries
│   │   └── scorer.py       # Deterministic scoring (0 to 100)
│   ├── requirements.txt
│   └── .env.example        # Copy to .env (which is git-ignored) and add your key
└── extension/
    ├── manifest.json       # Chrome MV3
    ├── background.js       # Service worker: orchestrates analysis
    ├── content.js          # Injects the floating panel into the page
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

### 1. Get a Gemini API key

1. Go to <https://aistudio.google.com/app/apikey>
2. Click **Create API Key**
3. Copy the key

### 2. Configure the backend

```bash
cd policyguard/backend
cp .env.example .env        # Windows (Command Prompt): copy .env.example .env
```

Open `.env` in any text editor and set your key:

```
GOOGLE_API_KEY=your_real_key_here
MODEL_NAME=gemini-3.7-flash
```

`MODEL_NAME` is only an example. Google renames and retires models over time, so if you get a "model not found" error, choose a current Flash model from the [Gemini models page](https://ai.google.dev/gemini-api/docs/models) that works with your key. Never commit `.env`.

### 3. Install Python dependencies

```bash
cd policyguard/backend
pip install -r requirements.txt
```

### 4. Start the backend

```bash
python main.py
```

You should see:

```
INFO:     Uvicorn running on http://localhost:8000
```

Check it by opening <http://localhost:8000/health>, which should return `{"status":"ok"}`.

### 5. Load the Chrome extension

1. Open Chrome and go to `chrome://extensions`
2. Turn on **Developer mode** (top right)
3. Click **Load unpacked**
4. Select the `policyguard/extension/` folder
5. The PolicyGuard icon appears in your toolbar

---

## Usage

1. Open any Privacy Policy or Terms of Service page, for example `reddit.com/help/privacypolicy` or `amazon.com/privacy`.
2. PolicyGuard auto-detects the page and starts analyzing.
3. A floating panel slides in from the right with the result.
4. Click the extension icon at any time for the full popup with all flags.

You can also click **Analyze This Page** in the popup to scan a page manually. See the privacy note below before using it on pages that are not public policies.

---

## Red flags detected

| Category | Severity | What it catches |
|---|---|---|
| **Data Selling** | High | Selling or renting your data to advertisers or third parties |
| **Mandatory Arbitration** | High | Waiving your right to sue in court |
| **Children's Data** | High | Collecting data from minors, weak age verification |
| **Broad Tracking** | Medium | Location, behavior, biometrics, device fingerprinting |
| **Data Retention** | Medium | Indefinite retention, data kept after account deletion |
| **Auto-Renewal** | Medium | Hard-to-cancel subscriptions, automatic charges |
| **ToS Changes** | Medium | Terms changed without notice, continued use counts as consent |
| **Government Sharing** | Low | Data shared with law enforcement beyond legal requirements |

---

## Scoring

```
Start: 100 points
  - 22 points per HIGH severity flag    (max 3 flags counted)
  - 12 points per MEDIUM severity flag  (max 4 flags counted)
  -  4 points per LOW severity flag     (max 5 flags counted)

Score 70 or more  ->  Green   (few flagged risks)
Score 40 to 69    ->  Yellow  (several flagged risks, read carefully)
Score below 40    ->  Red     (many or serious flagged risks)
```

The weights, caps, and thresholds are hand-chosen heuristics and have not been validated against any ground truth. A green rating does **not** mean a policy is safe. It only means fewer of the eight patterns above were found.

---

## API reference

### `POST /analyze`

**Request:**

```json
{
  "url": "https://example.com/privacy",
  "html_text": "<html>...</html>"
}
```

**Response** (illustrative example, with the summaries list shortened):

```json
{
  "url": "https://example.com/privacy",
  "score": 56,
  "rating": "yellow",
  "emoji": "🟡",
  "final_summary": "Caution: this site tracks your behavior broadly and can change terms without notice.",
  "summaries": [
    {
      "category": "BROAD_TRACKING",
      "summary": "This site tracks your location, browsing behavior, and device fingerprint.",
      "severity": "medium"
    }
  ],
  "breakdown": { "high": 0, "medium": 3, "low": 2 },
  "clauses_found": 47,
  "flags_found": 5,
  "analysis_time_ms": 2341
}
```

The breakdown matches the scoring formula: 100 - (3 x 12) - (2 x 4) = 56.

---

## Privacy

PolicyGuard sends data off your device, so it helps to know where it goes:

- The extension sends the page's HTML to **your own backend** on `localhost`.
- The pipeline's LLM steps send **text extracted from the page** (the clauses it classifies and the flags it summarizes) to **Google's Gemini API**, which is subject to Google's terms for the API.
- **Manual analysis works on any page.** Do not use **Analyze This Page** on pages that contain personal information, such as email, banking, or private documents, because extracted text could be sent to Gemini.
- Your API key stays in `backend/.env`, which is not committed.

---

## Limitations

- **Not legal advice.** The LLM can misread or miss clauses, and legal language is subtle.
- **A fixed list of eight patterns.** Anything outside those categories is not flagged.
- **Heuristic scoring.** The weights and thresholds are not validated, and no formal accuracy evaluation has been done.
- **Depends on page structure.** Extraction quality varies with how a site builds its HTML, and policies loaded dynamically or split across pages may be missed.
- **Local setup only.** The backend runs on your machine, and the extension is loaded in developer mode, not from the Chrome Web Store.
- **Rate limits.** The Gemini free tier has per-minute and per-day limits that vary by model and change over time.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Backend offline (red dot in popup) | Run `python main.py` in the `backend/` directory |
| "Could not extract policy text" | Go directly to the privacy policy page URL |
| Extension not auto-detecting | Click **Analyze This Page** manually in the popup |
| API key error | Check `GOOGLE_API_KEY` in `backend/.env` |
| "Model not found" or 404 error | Update `MODEL_NAME` in `.env` to a current Flash model from the Gemini models page |
| Rate limit error (429) | Free-tier limits vary by model and change over time. Wait a minute and retry |

---

## What I'm learning from it

This project combines a Chrome extension, a FastAPI backend, and a LangGraph pipeline. I am working through each part, starting with the deterministic scorer and extractor, and plan to add tests and a small evaluation on real policies.
