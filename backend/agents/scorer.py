"""
Scorer Agent
Aggregates flags into a deterministic score (0–100) and traffic-light rating.
Zero LLM cost — pure Python math.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from prompts import FINAL_SUMMARY_SYSTEM, FINAL_SUMMARY_USER

logger = logging.getLogger(__name__)

# Points deducted per severity level
DEDUCTIONS = {
    "high": 22,
    "medium": 12,
    "low": 4,
}

# Cap on how many flags of each severity count toward score deduction
SEVERITY_CAPS = {
    "high": 3,
    "medium": 4,
    "low": 5,
}

RATING_THRESHOLDS = {
    "green": 70,
    "yellow": 40,
}

EMOJI_MAP = {
    "green": "🟢",
    "yellow": "🟡",
    "red": "🔴",
}

SEVERITY_EMOJI = {
    "high": "🔴",
    "medium": "🟡",
    "low": "🟢",
}


def compute_score(summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate risk score from summarized flags.

    Returns:
        score: int 0–100
        rating: 'green' | 'yellow' | 'red'
        emoji: traffic-light emoji
        breakdown: counts per severity
    """
    score = 100
    counts = {"high": 0, "medium": 0, "low": 0}

    for item in summaries:
        sev = item.get("severity", "medium").lower()
        if sev not in counts:
            sev = "medium"

        if counts[sev] < SEVERITY_CAPS[sev]:
            score -= DEDUCTIONS[sev]
            counts[sev] += 1

    score = max(0, score)

    if score >= RATING_THRESHOLDS["green"]:
        rating = "green"
    elif score >= RATING_THRESHOLDS["yellow"]:
        rating = "yellow"
    else:
        rating = "red"

    logger.info(f"Scorer: score={score}, rating={rating}, breakdown={counts}")

    return {
        "score": score,
        "rating": rating,
        "emoji": EMOJI_MAP[rating],
        "breakdown": counts,
    }


async def generate_final_summary(
    rating: str,
    summaries: List[Dict[str, Any]],
    llm: ChatGoogleGenerativeAI,
) -> str:
    """Generate a one-sentence plain-English verdict using Gemini Flash."""
    if not summaries:
        return "✅ No significant risks found in this policy."

    # Sort by severity for the top risks
    sev_order = {"high": 0, "medium": 1, "low": 2}
    sorted_summaries = sorted(summaries, key=lambda x: sev_order.get(x.get("severity", "low"), 2))
    top = sorted_summaries[:3]
    top_risks = "; ".join(s["summary"] for s in top)

    messages = [
        SystemMessage(content=FINAL_SUMMARY_SYSTEM),
        HumanMessage(content=FINAL_SUMMARY_USER.format(
            rating=rating.upper(),
            top_risks=top_risks,
        )),
    ]

    try:
        response = await llm.ainvoke(messages)
        return response.content.strip()
    except Exception as e:
        logger.warning(f"Final summary LLM error: {e}")
        emoji = EMOJI_MAP.get(rating, "⚠️")
        return f"{emoji} {rating.capitalize()} policy — {top_risks[:100]}."
