"""
Risk-Flagger Agent
Scans extracted clauses for 8 categories of red flags.
Uses hybrid approach: fast regex pre-filter, then Gemini Flash for ambiguous clauses.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from prompts import RISK_FLAGGER_SYSTEM, RISK_FLAGGER_USER

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule-based pre-filter — catches obvious flags with zero LLM cost
# ---------------------------------------------------------------------------

RULE_PATTERNS: Dict[str, List[str]] = {
    "DATA_SELLING": [
        r"sell(ing)?\s+(your\s+)?(personal\s+)?data",
        r"sell(ing)?\s+(your\s+)?information",
        r"rent(ing)?\s+(your\s+)?(personal\s+)?data",
        r"share.{0,40}(advertis|market|partner|third.party)",
        r"disclose.{0,40}(advertis|partner|third.party)",
        r"monetize.{0,30}(data|information|profile)",
    ],
    "BROAD_TRACKING": [
        r"track(ing)?\s+(your\s+)?(location|behavior|browsing|activity)",
        r"collect.{0,40}(location|gps|geolocation)",
        r"fingerprint(ing)?",
        r"biometric(s)?",
        r"record(ing)?\s+(your\s+)?(calls|communications|screen)",
        r"monitor(ing)?\s+(your\s+)?(activity|behavior|usage)",
    ],
    "ARBITRATION": [
        r"binding\s+arbitration",
        r"mandatory\s+arbitration",
        r"waive.{0,30}(right|jury|class\s*action)",
        r"class\s*action\s*waiver",
        r"individual\s+basis\s+only",
        r"arbitrat(e|ion|or).{0,50}(dispute|claim|controversy)",
    ],
    "DATA_RETENTION": [
        r"retain.{0,40}(indefinitely|as\s+long\s+as\s+(we|necessary|required))",
        r"keep.{0,40}(indefinitely|as\s+long\s+as)",
        r"store.{0,40}indefinitely",
        r"data.{0,20}(never\s+deleted|not\s+deleted)",
        r"retain.{0,30}after\s+(account\s+)?(closure|termination|deletion)",
    ],
    "AUTO_RENEWAL": [
        r"auto(matically)?[\s-]renew(s|al|ed)?",
        r"automatically\s+charged",
        r"recurring\s+(charge|billing|payment)",
        r"subscription\s+(will\s+)?renew",
        r"cancel(lation)?\s+(before|prior)",
    ],
    "TOS_CHANGE": [
        r"(modify|change|update).{0,50}(terms|policy|agreement).{0,30}(notice|notification|consent)?",
        r"(terms|policy).{0,30}(may|can|will)\s+(be\s+)?(modified|changed|updated)\s+(at\s+any\s+time|without\s+notice)",
        r"continued\s+use.{0,50}constitutes\s+(acceptance|agreement)",
        r"without\s+(prior\s+)?notice",
    ],
    "GOV_SHARING": [
        r"law\s+enforcement",
        r"government(al)?\s+(request|order|authority|agency)",
        r"national\s+security",
        r"intelligence\s+agenc",
        r"court\s+order",
        r"subpoena",
        r"legal\s+process.{0,30}(disclose|share|provide)",
    ],
    "CHILDREN_DATA": [
        r"(collect|gather).{0,30}(data|information).{0,30}(children|minors|under\s+13)",
        r"(children|minors).{0,30}(data|information).{0,30}(collect|gather)",
        r"coppa",
        r"under\s+(the\s+age\s+of\s+)?(13|sixteen|18)",
        r"parental\s+consent",
    ],
}

SEVERITY_MAP: Dict[str, str] = {
    "DATA_SELLING": "high",
    "ARBITRATION": "high",
    "BROAD_TRACKING": "medium",
    "DATA_RETENTION": "medium",
    "AUTO_RENEWAL": "medium",
    "TOS_CHANGE": "medium",
    "GOV_SHARING": "low",
    "CHILDREN_DATA": "high",
}

COMPILED_PATTERNS = {
    cat: [re.compile(p, re.IGNORECASE) for p in patterns]
    for cat, patterns in RULE_PATTERNS.items()
}


def rule_based_flag(clauses: List[str]) -> List[Dict[str, Any]]:
    """Fast regex scan — no LLM calls."""
    flags: List[Dict[str, Any]] = []
    seen_categories = set()

    for clause in clauses:
        for category, patterns in COMPILED_PATTERNS.items():
            if category in seen_categories:
                continue  # one flag per category is enough for scoring
            for pattern in patterns:
                match = pattern.search(clause)
                if match:
                    # Extract a short snippet around the match
                    start = max(0, match.start() - 40)
                    end = min(len(clause), match.end() + 80)
                    snippet = clause[start:end].strip()
                    if len(snippet) > 120:
                        snippet = snippet[:120] + "…"

                    flags.append({
                        "category": category,
                        "clause_snippet": snippet,
                        "severity": SEVERITY_MAP[category],
                        "source": "rule",
                    })
                    seen_categories.add(category)
                    break

    return flags


async def llm_flag(
    clauses: List[str],
    url: str,
    llm: ChatGoogleGenerativeAI,
    already_found: set,
) -> List[Dict[str, Any]]:
    """
    Send a batch of clauses to Gemini Flash for classification.
    Only called for categories NOT already caught by rules.
    """
    missing_cats = set(RULE_PATTERNS.keys()) - already_found
    if not missing_cats or not clauses:
        return []

    # Sample up to 30 clauses (avoid huge prompts)
    sample = clauses[:30]
    clauses_text = "\n\n---\n\n".join(sample)

    messages = [
        SystemMessage(content=RISK_FLAGGER_SYSTEM),
        HumanMessage(content=RISK_FLAGGER_USER.format(url=url, clauses=clauses_text)),
    ]

    try:
        response = await llm.ainvoke(messages)
        raw = response.content.strip()

        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []

        llm_flags = []
        for item in parsed:
            cat = item.get("category", "").upper()
            if cat in RULE_PATTERNS and cat not in already_found:
                llm_flags.append({
                    "category": cat,
                    "clause_snippet": str(item.get("clause_snippet", ""))[:200],
                    "severity": item.get("severity", SEVERITY_MAP.get(cat, "medium")),
                    "source": "llm",
                })
        return llm_flags

    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"LLM risk-flagger error: {e}")
        return []


async def flag_risks(
    clauses: List[str],
    url: str,
    llm: ChatGoogleGenerativeAI,
) -> List[Dict[str, Any]]:
    """
    Main entry point for the Risk-Flagger agent.
    1. Run fast rule-based pass first.
    2. Run LLM only for categories not already found.
    """
    rule_flags = rule_based_flag(clauses)
    found_cats = {f["category"] for f in rule_flags}

    llm_flags = await llm_flag(clauses, url, llm, found_cats)

    all_flags = rule_flags + llm_flags
    logger.info(f"Risk-Flagger: {len(rule_flags)} rule flags + {len(llm_flags)} LLM flags = {len(all_flags)} total")
    return all_flags
