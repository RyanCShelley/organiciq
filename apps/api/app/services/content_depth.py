"""Content-depth scoring, ported from Topic Hub (v2/content_depth.py) unchanged in what it measures.

Grader heuristics at per-page granularity.

Pure text signals over the cleaned body: does the page contain the kind
of specific, extract-worthy content LLMs like to cite? Numbers, dates,
named people, monetary figures, length + structure.

Returned as a 0–100 score plus a signals dict so the drawer can show
what's there and what's missing. Not folded into citation_potential —
lives alongside so the two remain independently interpretable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ContentDepthResult:
    score: int
    signals: dict[str, Any]


_MONTH = r"january|february|march|april|may|june|july|august|september|october|november|december"


def score_content_depth(text: str | None) -> ContentDepthResult:
    """Return depth score + signals dict for a body of cleaned text.

    Scale (roughly):
      0–29  thin / generic
      30–59 some substance
      60–89 rich
      90+   deeply data-rich
    """
    body = (text or "").strip()
    if not body:
        return ContentDepthResult(score=0, signals={"empty": True})

    signals: dict[str, Any] = {}
    score = 0

    # 1) Numbers + percentages + dollar figures (20 pts, up to 3 tiers)
    pct_count = len(re.findall(r"\b\d+(?:\.\d+)?\s*%", body))
    money_count = len(re.findall(r"\$[\d,]+(?:\.\d+)?[kmb]?", body, re.I))
    year_count = len(re.findall(r"\b(?:19|20)\d{2}\b", body))
    stat_hits = pct_count + money_count + year_count
    if stat_hits >= 6:
        score += 20
    elif stat_hits >= 3:
        score += 12
    elif stat_hits >= 1:
        score += 5
    signals["stats_hits"] = stat_hits

    # 2) Full dates ("March 12, 2024") — freshness marker (10 pts)
    date_count = len(re.findall(rf"\b({_MONTH})\b\s+\d{{1,2}},?\s*\d{{4}}", body, re.I))
    if date_count >= 2:
        score += 10
    elif date_count >= 1:
        score += 5
    signals["dates_present"] = date_count

    # 3) Named people — CEO / founder / director / manager (15 pts)
    role_count = len(re.findall(
        r"\b(?:CEO|CFO|CTO|COO|founder|co-?founder|president|director|VP|manager|author|editor)\b",
        body, re.I,
    ))
    if role_count >= 3:
        score += 15
    elif role_count >= 1:
        score += 8
    signals["role_mentions"] = role_count

    # 4) Structured content — lists, tables, code (15 pts)
    list_hits = len(re.findall(r"(?:\n|^)\s*(?:[-•*]|\d+\.)\s", body))
    table_marker = bool(re.search(r"\|.*\|.*\|", body))
    if list_hits >= 5 or table_marker:
        score += 15
    elif list_hits >= 2:
        score += 8
    signals["list_items"] = list_hits
    signals["table_present"] = table_marker

    # 5) Length as coarse proxy — but only when combined with the above
    # (long-and-vague shouldn't beat short-and-specific)
    word_count = len(body.split())
    if word_count >= 1500:
        score += 15
    elif word_count >= 800:
        score += 10
    elif word_count >= 400:
        score += 5
    signals["word_count"] = word_count

    # 6) Contact / trust markers — phone number, address (10 pts)
    trust = 0
    if re.search(r"\(\d{3}\)\s*\d{3}[-.]?\d{4}", body):
        trust += 5
        signals["phone_present"] = True
    if re.search(r"\b\d+\s+\w+\s+(?:st|street|ave|avenue|blvd|road|rd|drive|dr)\b", body, re.I):
        trust += 5
        signals["address_present"] = True
    score += trust

    # 7) Quoted claims / attributed sources (15 pts)
    quote_count = len(re.findall(r'"[^"]{20,200}"', body))
    citation_marker = bool(re.search(
        r"\b(?:according to|as reported by|source:|cited by|based on|per\s+\w+'s report)\b",
        body, re.I,
    ))
    if quote_count >= 3 or (quote_count >= 1 and citation_marker):
        score += 15
    elif quote_count >= 1 or citation_marker:
        score += 8
    signals["quotes"] = quote_count
    signals["citation_marker"] = citation_marker

    total = min(score, 100)
    return ContentDepthResult(score=total, signals=signals)
