"""
PolicyGuard — LangGraph State Machine
Defines the PolicyState TypedDict and the 4-node pipeline:
  START → extractor → risk_flagger → summarizer → scorer → END

Conditional retry edge: extractor retries up to MAX_RETRIES times
if extraction quality is too low.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langchain_google_genai import ChatGoogleGenerativeAI

from agents.extractor import extract_clauses
from agents.risk_flagger import flag_risks
from agents.summarizer import summarize_flags
from agents.scorer import compute_score, generate_final_summary

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
QUALITY_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class PolicyState(TypedDict):
    # Input
    url: str
    raw_html: str

    # Extractor outputs
    clauses: List[str]
    extraction_quality: float
    extraction_retries: int

    # Risk-Flagger outputs
    flags: List[Dict[str, Any]]

    # Summarizer outputs
    summaries: List[Dict[str, Any]]

    # Scorer outputs
    score: int
    rating: str
    emoji: str
    breakdown: Dict[str, int]
    final_summary: str

    # Error channel
    error: Optional[str]


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def extractor_node(state: PolicyState) -> PolicyState:
    """Extract and clean clauses from raw HTML."""
    try:
        clauses, quality = extract_clauses(state["raw_html"])
        retries = state.get("extraction_retries", 0)

        if not clauses and retries < MAX_RETRIES:
            logger.warning(f"Extractor: empty result, retry {retries + 1}")

        return {
            **state,
            "clauses": clauses,
            "extraction_quality": quality,
            "extraction_retries": state.get("extraction_retries", 0),
        }
    except Exception as e:
        logger.error(f"Extractor node error: {e}")
        return {**state, "error": f"Extraction failed: {str(e)}", "clauses": [], "extraction_quality": 0.0}


async def risk_flagger_node(state: PolicyState) -> PolicyState:
    """Scan clauses for red flags using hybrid rule+LLM approach."""
    try:
        llm = _get_llm()
        flags = await flag_risks(state["clauses"], state["url"], llm)
        return {**state, "flags": flags}
    except Exception as e:
        logger.error(f"Risk-Flagger node error: {e}")
        return {**state, "flags": [], "error": f"Risk flagging failed: {str(e)}"}


async def summarizer_node(state: PolicyState) -> PolicyState:
    """Convert flags to plain-English summaries."""
    try:
        llm = _get_llm()
        summaries = await summarize_flags(state["flags"], llm)
        return {**state, "summaries": summaries}
    except Exception as e:
        logger.error(f"Summarizer node error: {e}")
        return {**state, "summaries": [], "error": f"Summarization failed: {str(e)}"}


async def scorer_node(state: PolicyState) -> PolicyState:
    """Compute numeric score and generate final verdict."""
    try:
        score_data = compute_score(state["summaries"])
        llm = _get_llm()
        final_summary = await generate_final_summary(
            score_data["rating"], state["summaries"], llm
        )
        return {
            **state,
            "score": score_data["score"],
            "rating": score_data["rating"],
            "emoji": score_data["emoji"],
            "breakdown": score_data["breakdown"],
            "final_summary": final_summary,
        }
    except Exception as e:
        logger.error(f"Scorer node error: {e}")
        return {
            **state,
            "score": 50,
            "rating": "yellow",
            "emoji": "🟡",
            "breakdown": {},
            "final_summary": "Unable to generate verdict.",
            "error": f"Scoring failed: {str(e)}",
        }


# ---------------------------------------------------------------------------
# Conditional edge: retry extractor or proceed
# ---------------------------------------------------------------------------

def should_retry_extraction(state: PolicyState) -> str:
    """
    Route after extractor:
    - 'retry'   → loop back to extractor (quality too low, retries remaining)
    - 'proceed' → continue to risk_flagger
    - 'fail'    → go to END (too many retries, no content)
    """
    if state.get("error"):
        return "fail"

    quality = state.get("extraction_quality", 0.0)
    retries = state.get("extraction_retries", 0)

    if quality >= QUALITY_THRESHOLD or len(state.get("clauses", [])) > 5:
        return "proceed"

    if retries < MAX_RETRIES:
        return "retry"

    return "fail"


def increment_retry(state: PolicyState) -> PolicyState:
    """Increment retry counter before looping back to extractor."""
    return {**state, "extraction_retries": state.get("extraction_retries", 0) + 1}


def fail_node(state: PolicyState) -> PolicyState:
    """Graceful failure when extraction cannot produce usable content."""
    return {
        **state,
        "score": -1,
        "rating": "unknown",
        "emoji": "❓",
        "breakdown": {},
        "final_summary": "Could not extract policy text from this page. Try navigating directly to the Privacy Policy or ToS page.",
        "error": state.get("error") or "Extraction quality too low after retries.",
    }


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=os.getenv("MODEL_NAME", "gemini-1.5-flash"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.1,
    )


def build_graph() -> StateGraph:
    """Construct and compile the LangGraph pipeline."""
    graph = StateGraph(PolicyState)

    # Add nodes
    graph.add_node("extractor", extractor_node)
    graph.add_node("retry_increment", increment_retry)
    graph.add_node("risk_flagger", risk_flagger_node)
    graph.add_node("summarizer", summarizer_node)
    graph.add_node("scorer", scorer_node)
    graph.add_node("fail", fail_node)

    # Entry point
    graph.add_edge(START, "extractor")

    # Conditional routing after extractor
    graph.add_conditional_edges(
        "extractor",
        should_retry_extraction,
        {
            "proceed": "risk_flagger",
            "retry": "retry_increment",
            "fail": "fail",
        },
    )

    # Retry loop
    graph.add_edge("retry_increment", "extractor")

    # Main pipeline
    graph.add_edge("risk_flagger", "summarizer")
    graph.add_edge("summarizer", "scorer")
    graph.add_edge("scorer", END)
    graph.add_edge("fail", END)

    return graph.compile()


# Singleton compiled graph
compiled_graph = build_graph()
