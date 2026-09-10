"""
Extractor Agent
Locates and cleans ToS/Privacy Policy text from raw HTML.
Uses BeautifulSoup heuristics — zero LLM cost.
"""

from __future__ import annotations

import re
import logging
from typing import List, Tuple

from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)

# CSS selectors / id/class keywords that strongly signal policy content
POLICY_SELECTORS = [
    "article", "main", "[role='main']",
    "#content", "#main", "#privacy", "#terms", "#tos", "#legal",
]

POLICY_KEYWORDS = re.compile(
    r"(privacy|terms|policy|tos|legal|conditions|agreement|cookies|gdpr|ccpa)",
    re.IGNORECASE,
)

# Tags that are always boilerplate
NOISE_TAGS = {
    "nav", "header", "footer", "aside", "form",
    "button", "script", "style", "noscript", "iframe",
    "img", "svg", "figure", "figcaption", "picture",
}

# Minimum meaningful clause length (characters)
MIN_CLAUSE_LEN = 60
# Maximum clause length before we split (characters)
MAX_CLAUSE_LEN = 600


def extract_clauses(raw_html: str) -> Tuple[List[str], float]:
    """
    Parse raw HTML and return a list of cleaned clause strings plus a
    quality score (0.0–1.0) indicating how confident we are that we
    found real policy text.

    Returns:
        clauses: list of cleaned text segments
        quality: float 0.0–1.0
    """
    if not raw_html or not raw_html.strip():
        return [], 0.0

    soup = BeautifulSoup(raw_html, "lxml")

    # Remove noise tags entirely
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()

    # Remove HTML comments
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # Try to find the most specific policy container
    target_element = _find_policy_container(soup)

    if target_element:
        text = target_element.get_text(separator="\n", strip=True)
        quality_base = 0.85
    else:
        # Fall back to full body
        body = soup.find("body")
        text = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)
        quality_base = 0.45

    clauses = _split_into_clauses(text)
    quality = _estimate_quality(clauses, quality_base)

    logger.info(f"Extractor: {len(clauses)} clauses, quality={quality:.2f}")
    return clauses, quality


def _find_policy_container(soup: BeautifulSoup):
    """Try selectors and keyword-matching to find the best policy container."""
    # 1. Try explicit selectors
    for selector in POLICY_SELECTORS:
        el = soup.select_one(selector)
        if el and len(el.get_text(strip=True)) > 500:
            return el

    # 2. Scan all divs/sections for policy-related id/class
    for tag in soup.find_all(["div", "section", "article", "main"]):
        id_val = tag.get("id", "")
        class_val = " ".join(tag.get("class", []))
        combined = f"{id_val} {class_val}"
        if POLICY_KEYWORDS.search(combined):
            text_len = len(tag.get_text(strip=True))
            if text_len > 500:
                return tag

    # 3. Find the div with the most text (likely the content area)
    candidates = soup.find_all(["div", "section", "article"])
    if candidates:
        best = max(candidates, key=lambda t: len(t.get_text(strip=True)), default=None)
        if best and len(best.get_text(strip=True)) > 1000:
            return best

    return None


def _split_into_clauses(text: str) -> List[str]:
    """Split cleaned text into meaningful clause-sized chunks."""
    # Split on double newlines (paragraphs), then on sentence boundaries
    raw_paragraphs = re.split(r"\n{2,}", text)

    clauses: List[str] = []
    for para in raw_paragraphs:
        para = para.strip()
        # Normalize internal whitespace
        para = re.sub(r"[ \t]+", " ", para)
        para = re.sub(r"\n+", " ", para)

        if len(para) < MIN_CLAUSE_LEN:
            continue  # skip headings, short lines

        if len(para) <= MAX_CLAUSE_LEN:
            clauses.append(para)
        else:
            # Split long paragraph into sentences
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", para)
            buf = ""
            for sent in sentences:
                if len(buf) + len(sent) < MAX_CLAUSE_LEN:
                    buf = (buf + " " + sent).strip()
                else:
                    if len(buf) >= MIN_CLAUSE_LEN:
                        clauses.append(buf)
                    buf = sent
            if len(buf) >= MIN_CLAUSE_LEN:
                clauses.append(buf)

    return clauses[:150]  # cap at 150 clauses to avoid token explosion


def _estimate_quality(clauses: List[str], base: float) -> float:
    """Heuristic quality score based on clause count and keyword density."""
    if not clauses:
        return 0.0

    total_text = " ".join(clauses)
    word_count = len(total_text.split())

    # Penalize very few clauses
    if len(clauses) < 3:
        base *= 0.4
    elif len(clauses) < 8:
        base *= 0.7

    # Boost if policy keywords appear
    keyword_hits = len(POLICY_KEYWORDS.findall(total_text))
    if keyword_hits > 10:
        base = min(base + 0.1, 1.0)

    # Penalize if it looks like a generic page (too few words)
    if word_count < 200:
        base *= 0.5

    return round(base, 2)
