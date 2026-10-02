"""How much work a finding is, as a size rather than a number. S1.

The engine already carries an `effort` of 0-100 per lever, which feeds the
priority score at a weight of 0.1. That number is per *lever*, so every
Technical SEO finding costs 45 whether it is a title rewrite or a migration,
and the difference between twenty minutes and two weeks never reaches the
queue.

Sizes are per rule, not per lever, and they re-order rather than re-score:
promotion still turns on impact and confidence, so nothing is promoted or
blocked because of how long it takes. What changes is which of the work
already worth doing comes first — and between two findings worth the same,
the cheaper one should.
"""

from __future__ import annotations

from typing import Any, Mapping

SMALL, MEDIUM, LARGE = "S", "M", "L"

#: Size by rule, from the audit signal or gate the finding carries.
#: Anything unlisted falls back to the lever default below.
EFFORT_BY_SIGNAL: dict[str, str] = {
    # Edits to one field on one page.
    "title_missing": SMALL,
    "title_duplicate": SMALL,
    "description_missing": SMALL,
    "description_duplicate": SMALL,
    "missing_meta": SMALL,
    "duplicate_meta": SMALL,
    "orphan_page": SMALL,
    "internal_linking": SMALL,
    "link_reclamation": SMALL,
    # A page's worth of work.
    "missing_schema": MEDIUM,
    "invalid_schema": MEDIUM,
    "light_refresh": MEDIUM,
    "serp_ctr": MEDIUM,
    "conversion_page": MEDIUM,
    "status_error": MEDIUM,
    "broken_redirect": MEDIUM,
    "redirect_chain": MEDIUM,
    "non_indexable": MEDIUM,
    "canonical_elsewhere": MEDIUM,
    # A new page, or rewriting one against a different intent.
    "content_cluster": LARGE,
    "deep_refresh": LARGE,
    "keyword_not_ranking": LARGE,
    "prompt_not_cited": LARGE,
    "ai_sov_falling": LARGE,
}

EFFORT_BY_LEVER: dict[str, str] = {
    "serp_ctr": SMALL,
    "internal_linking": SMALL,
    "technical_seo": MEDIUM,
    "conversion_path": MEDIUM,
    "structured_data_ai": LARGE,
}

WEIGHT_KEYS = {SMALL: "effort_weight_small", MEDIUM: "effort_weight_medium", LARGE: "effort_weight_large"}


def effort_class(lever: str, evidence: Mapping[str, Any]) -> str:
    signal = evidence.get("audit_signal") or evidence.get("gate")
    if signal and str(signal) in EFFORT_BY_SIGNAL:
        return EFFORT_BY_SIGNAL[str(signal)]
    return EFFORT_BY_LEVER.get(lever, MEDIUM)


def ranking_score(
    *, impact: float, confidence: float, effort: str, thresholds: Mapping[str, Any]
) -> float:
    """impact × confidence ÷ effort weight, as the review specified."""
    weight = float(thresholds.get(WEIGHT_KEYS.get(effort, ""), 1.0)) or 1.0
    return round((float(impact) * float(confidence) / 100.0) / weight, 2)
