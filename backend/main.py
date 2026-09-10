"""
PolicyGuard Backend — FastAPI Application
Exposes POST /analyze endpoint for the browser extension.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from graph import compiled_graph

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("policyguard")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="PolicyGuard API",
    description="LangGraph-powered ToS & Privacy Policy risk analyzer",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Extension sends from chrome-extension:// origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="URL of the page being analyzed")
    html_text: str = Field(..., description="Full HTML content of the page")


class FlagSummary(BaseModel):
    category: str
    summary: str
    severity: str


class AnalyzeResponse(BaseModel):
    url: str
    score: int
    rating: str
    emoji: str
    final_summary: str
    summaries: List[FlagSummary]
    breakdown: Dict[str, int]
    clauses_found: int
    flags_found: int
    analysis_time_ms: int
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "policyguard"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    """
    Run the LangGraph pipeline on the provided page HTML.
    Returns a structured risk analysis with score, rating, and plain-English summaries.
    """
    if not req.html_text or len(req.html_text.strip()) < 100:
        raise HTTPException(status_code=400, detail="html_text is too short or empty")

    if not os.getenv("GOOGLE_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_API_KEY not configured. Set it in backend/.env",
        )

    logger.info(f"Analyzing: {req.url} ({len(req.html_text):,} chars)")
    start_time = time.time()

    initial_state = {
        "url": req.url,
        "raw_html": req.html_text,
        "clauses": [],
        "extraction_quality": 0.0,
        "extraction_retries": 0,
        "flags": [],
        "summaries": [],
        "score": 0,
        "rating": "unknown",
        "emoji": "❓",
        "breakdown": {},
        "final_summary": "",
        "error": None,
    }

    try:
        final_state = await compiled_graph.ainvoke(initial_state)
    except Exception as e:
        logger.error(f"Graph execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis pipeline failed: {str(e)}")

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"Done: score={final_state.get('score')}, "
        f"rating={final_state.get('rating')}, "
        f"time={elapsed_ms}ms"
    )

    return AnalyzeResponse(
        url=req.url,
        score=final_state.get("score", -1),
        rating=final_state.get("rating", "unknown"),
        emoji=final_state.get("emoji", "❓"),
        final_summary=final_state.get("final_summary", ""),
        summaries=[FlagSummary(**s) for s in final_state.get("summaries", [])],
        breakdown=final_state.get("breakdown", {}),
        clauses_found=len(final_state.get("clauses", [])),
        flags_found=len(final_state.get("flags", [])),
        analysis_time_ms=elapsed_ms,
        error=final_state.get("error"),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.getenv("HOST", "localhost")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
