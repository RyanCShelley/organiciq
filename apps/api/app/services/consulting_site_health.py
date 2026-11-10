"""Site health for the consulting reports: the two scores and what sits under them, in the shape a client reads.

It reads the screen's own monthly scores (services/site_health), so a report and the Site health screen never disagree.
Only the scores, the checks behind them and the counts of new and fixed pages are carried: no page lists, no fixes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.client import Client
from app.services import site_health


def _delta(now: int, was: int | None) -> int | None:
    return None if was is None else now - was


def build(db: Session, client: Client, month: str) -> dict[str, Any] | None:
    """The month's SEO health and GEO readiness, or None when the site has no score for that month."""
    data = site_health.for_month(db, client, month)
    if data is None:
        return None
    prev = data.get("previous") or {}
    seo, geo = data["seo"], data["geo"]
    crawl = data.get("crawl") or {}
    fixed = sum(c["fixed_count"] for c in data.get("changes", []))
    new = sum(c["new_count"] for c in data.get("changes", []))
    return {
        "month": month,
        "crawl_date": data.get("crawl_date"),
        "pages": seo.get("pages"),
        "hit_limit": bool(crawl.get("hit_limit")),
        "previous_month": prev.get("month"),
        "seo": {"score": seo["score"], "grade": seo["grade"], "previous": prev.get("seo"), "change": _delta(seo["score"], prev.get("seo")),
                "checks": [{"label": c["label"], "score": c["score"], "affected": c["affected"], "total": c["total"]} for c in seo["checks"]]},
        "geo": {"score": geo["score"], "grade": geo["grade"], "previous": prev.get("geo"), "change": _delta(geo["score"], prev.get("geo")), "partial": bool(geo.get("partial")),
                "signals": [{"label": s["label"], "score": s["score"] if s["measured"] else None, "summary": s.get("summary")} for s in geo["signals"]]},
        "new_issues": new if prev else None, "fixed_issues": fixed if prev else None,
        "source": "Organic IQ site crawl",
    }
