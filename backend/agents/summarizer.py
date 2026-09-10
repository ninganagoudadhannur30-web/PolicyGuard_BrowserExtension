"""
Summarizer Agent
Converts flagged clauses into plain-English one-line explanations via Gemini Flash.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from prompts import SUMMARIZER_SYSTEM, SUMMARIZER_USER

logger = logging.getLogger(__name__)

# Fallback summaries if LLM fails, keyed by category
FALLBACK_SUMMARIES: Dict[str, str] = {
    "DATA_SELLING": "This site may sell your personal data to third parties.",
    "BROAD_TRACKING": "This site tracks your behavior, location, or device extensively.",
    "ARBITRATION": "You waive your right to sue in court — disputes go to arbitration.",
    "DATA_RETENTION": "Your data may be kept indefinitely, even after you delete your account.",
    "AUTO_RENEWAL": "Your subscription renews automatically and may be hard to cancel.",
    "TOS_CHANGE": "This site can change its terms at any time without notifying you.",
    "GOV_SHARING": "This site shares your data with government or law enforcement on request.",
    "CHILDREN_DATA": "This site may collect data from children or has weak age verification.",
}


async def summarize_flags(
    flags: List[Dict[str, Any]],
    llm: ChatGoogleGenerativeAI,
) -> List[Dict[str, Any]]:
    """
    For each flag, produce a plain-English one-sentence summary.
    Sends all flags in one batch call to minimize API round-trips.
    """
    if not flags:
        return []

    flags_json = json.dumps(flags, indent=2)

    messages = [
        SystemMessage(content=SUMMARIZER_SYSTEM),
        HumanMessage(content=SUMMARIZER_USER.format(flags_json=flags_json)),
    ]

    try:
        response = await llm.ainvoke(messages)
        raw = response.content.strip()

        # Strip markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("Expected JSON array")

        # Validate and clean each item
        summaries = []
        for item in parsed:
            cat = str(item.get("category", "")).upper()
            summaries.append({
                "category": cat,
                "summary": str(item.get("summary", FALLBACK_SUMMARIES.get(cat, "Unknown risk detected."))),
                "severity": str(item.get("severity", "medium")),
            })

        logger.info(f"Summarizer: produced {len(summaries)} summaries via LLM")
        return summaries

    except (json.JSONDecodeError, ValueError, Exception) as e:
        logger.warning(f"Summarizer LLM error: {e}. Using fallback summaries.")
        # Fallback: use hardcoded summaries
        return [
            {
                "category": f["category"],
                "summary": FALLBACK_SUMMARIES.get(f["category"], "Risk detected in this policy."),
                "severity": f.get("severity", "medium"),
            }
            for f in flags
        ]
