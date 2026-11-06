"""The consulting report: a few headline numbers (Data), the consultant's own words (Analysis), then the action plan.

The numbers come from the monthly review and its scorecards, the same figures the rest of Organic IQ shows, never a second pipeline. They are shaped for a
client reader: plain labels, this month against last, where each number comes from, and a plain note wherever tracking is missing or a number is only a sample.
Nothing is estimated to fill a gap: a number that is not there says so.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.consulting import ConsultingReport
from app.services import bi, monthly_review, review_scorecards, review_visibility


class ReportError(ValueError):
    pass


class ReportConflict(ReportError):
    pass


def _m(label: str, cur: Any, prev: Any, pct: Any, *, source: str, unit: str = "", lower_is_better: bool = False, note: str | None = None) -> dict[str, Any]:
    return {"label": label, "current": cur, "previous": prev, "change_pct": pct, "unit": unit, "source": source, "lower_is_better": lower_is_better, "note": note}


def _pair(p: dict | None) -> tuple[Any, Any, Any]:
    p = p or {}
    return p.get("current"), p.get("previous"), p.get("change_pct")


def shape(review: dict[str, Any], cards: dict[str, Any]) -> dict[str, Any]:
    """The headline numbers for a client: Visibility, Traffic, Leads. Pure, so it is tested without data."""
    search = review.get("search") or {}
    vis = cards.get("visibility") or {}
    traffic = cards.get("traffic") or {}
    conv = cards.get("conversions") or {}
    reads = cards.get("reads") or {}
    fresh = [f.get("source") for f in (review.get("freshness") or []) if f and f.get("available") is False and f.get("source")]

    visibility: list[dict] = []
    if review.get("has_search_data"):
        i = _pair(search.get("impressions"))
        c = _pair(search.get("clicks"))
        p = _pair(search.get("average_position"))
        visibility += [
            _m("Search impressions", *i, source="Google Search Console"),
            _m("Search clicks", *c, source="Google Search Console"),
            _m("Average position", *p, source="Google Search Console", lower_is_better=True, note="Lower is better."),
        ]
    if vis.get("available") and vis.get("headline") is not None:
        visibility.append(_m("Tracked terms showing in Google", vis["headline"], None, None, source="Your tracked keywords", unit=f"of {vis.get('of')}"))
    if vis.get("ai_mentions") is not None:
        runs = vis.get("ai_runs")
        visibility.append(_m("AI answers that name you", vis["ai_mentions"], None, None, source="AI platform checks", note=f"A sample from {runs} check{'s' if runs != 1 else ''}, not every AI answer." if runs else "A sample, not every AI answer."))
    if vis.get("ai_links") is not None:
        visibility.append(_m("AI answers that link to you", vis["ai_links"], None, None, source="AI platform checks", note="A sample."))

    t_rows = [_m("Website visits", traffic.get("headline"), traffic.get("previous"), traffic.get("change_pct"), source="Google Analytics")] if traffic.get("headline") is not None else []
    for ch in traffic.get("channels") or []:
        if ch.get("key") == "organic_search":
            t_rows.append(_m("Visits from search", ch.get("sessions"), ch.get("previous"), ch.get("change_pct"), source="Google Analytics"))
        if ch.get("key") == "ai_referral":
            t_rows.append(_m("Visits from AI assistants", ch.get("sessions"), ch.get("previous"), ch.get("change_pct"), source="Google Analytics", note="Counted only where the visit says it came from an AI assistant. It is never guessed from direct visits."))

    noun = conv.get("noun") or "leads"
    l_rows = []
    if conv.get("headline") is not None:
        l_rows.append(_m(f"{noun[:1].upper() + noun[1:]} tracked", conv.get("headline"), conv.get("previous"), conv.get("change_pct"), source="Google Analytics key events"))
    rate = conv.get("conversion_rate") or {}
    if rate.get("current") is not None:
        l_rows.append(_m("Lead rate", rate.get("current"), rate.get("previous"), rate.get("change_pct"), source="Google Analytics", unit="%"))
    if conv.get("revenue") is not None:
        l_rows.append(_m("Revenue", conv["revenue"], None, None, source="Google Analytics purchases"))
    leads_note = None
    if (conv.get("headline") in (0, None)) and (traffic.get("headline") or 0) > 0:
        leads_note = f"No {noun} are tracked for this month even though the site has visits. If it should be producing them, tracking may be incomplete. We have not filled the gap with an estimate."

    return {
        "month": review.get("month"), "previous_month": review.get("previous_month"),
        "headline": cards.get("headline"),
        "sections": [
            {"key": "visibility", "label": "Visibility", "question": "Are we being found?", "metrics": visibility, "read": reads.get("visibility"), "limitation": None if visibility else "No search data is connected for this period."},
            {"key": "traffic", "label": "Traffic", "question": "Who is coming to the website?", "metrics": t_rows, "read": reads.get("traffic"), "limitation": None if t_rows else "No website visit data is connected for this period."},
            {"key": "leads", "label": "Leads", "question": "Is visibility producing business results?", "metrics": l_rows, "read": reads.get("conversions"), "limitation": leads_note or (None if l_rows else "No lead tracking is connected for this period.")},
        ],
        "caveats": ([f"No data yet from: {', '.join(fresh)}."] if fresh else []) + ["Comparisons are this month against last month. A change after any work is done may not be caused by that work alone."],
    }


#: What of the monthly review a client may be shown: the figures and the notes about them. Everything else in that payload (who locked it, the plan's work
#: counts, the model setting) stays internal. An allow-list, so a key added to the review later is not shown until it is listed here.
REVIEW_FIELDS = (
    "month", "previous_month", "noun", "conversions", "conversion_rate", "organic_conversions", "sessions", "organic_sessions", "search", "has_search_data", "goal",
    "channels", "top_pages", "services", "freshness", "revenue", "visibility", "summary", "data_through",
)


def client_review(review: dict[str, Any]) -> dict[str, Any]:
    return {k: review[k] for k in REVIEW_FIELDS if k in review}


def headline(db: Session, client: Client, month: str) -> dict[str, Any]:
    """The month's numbers, worked out now: the monthly review's own sections (Visibility, Traffic, Leads), and a little more from Insights."""
    try:
        first, last = monthly_review.parse_month(month)
    except ValueError as exc:
        raise ReportError(str(exc)) from exc
    review = monthly_review.review_for(db, client, month)
    cards = review_scorecards.build(db, client, review)
    insights = bi.build(db, client, first, last)
    return jsonable_encoder({
        **shape(review, cards), "as_of": review.get("data_through"), "locked": bool(review.get("locked")),
        "review": client_review(review), "cards": cards, "visibility_detail": review_visibility.llm_prompts(db, client, month),
        "insights": {"keywords": insights.get("keywords"), "ai": insights.get("ai"), "key_events": [e.get("name") or e.get("event") for e in insights.get("key_events") or []]},
    })


def get(db: Session, client: Client, month: str) -> ConsultingReport | None:
    return db.query(ConsultingReport).filter(ConsultingReport.client_id == client.id, ConsultingReport.period_month == month).one_or_none()


def save(db: Session, client: Client, month: str, *, analysis: str | None, title: str | None, revision: int | None, who: str) -> ConsultingReport:
    """Write the consultant's analysis. A saved report is edited with the revision it was opened at; a stale one is refused."""
    monthly_review.parse_month(month)
    rep = get(db, client, month)
    if rep is None:
        rep = ConsultingReport(client_id=client.id, period_month=month, revision=1)
        db.add(rep)
    else:
        if revision != rep.revision:
            raise ReportConflict("This report changed in another window. Reload it before saving.")
        rep.revision += 1
    rep.analysis = (analysis or "").strip() or None
    rep.title = (title or "").strip() or None
    rep.updated_by = who
    db.commit()
    db.refresh(rep)
    return rep


def publish(db: Session, client: Client, rep: ConsultingReport, who: str) -> ConsultingReport:
    """Show the report to the client, with the numbers as they stand now."""
    if not rep.analysis:
        raise ReportError("Write your analysis before publishing: the client reads the numbers alongside your words.")
    rep.metrics_snapshot = headline(db, client, rep.period_month)  # already plain JSON
    rep.review_state, rep.published_at, rep.published_by = "published", datetime.now(timezone.utc), who
    rep.revision += 1
    db.commit()
    db.refresh(rep)
    return rep


def unpublish(db: Session, rep: ConsultingReport) -> ConsultingReport:
    rep.review_state = "draft"
    rep.revision += 1
    db.commit()
    db.refresh(rep)
    return rep


def latest_published(db: Session, client: Client) -> ConsultingReport | None:
    return db.query(ConsultingReport).filter(ConsultingReport.client_id == client.id, ConsultingReport.review_state == "published").order_by(ConsultingReport.period_month.desc()).first()


def staff_out(rep: ConsultingReport | None, month: str) -> dict[str, Any]:
    return {
        "month": month, "title": rep.title if rep else None, "analysis": rep.analysis if rep else None, "review_state": rep.review_state if rep else "draft",
        "revision": rep.revision if rep else 0, "exists": rep is not None, "published_at": rep.published_at.isoformat() if rep and rep.published_at else None,
        "published_by": rep.published_by if rep else None, "updated_by": rep.updated_by if rep else None,
    }


def client_out(rep: ConsultingReport) -> dict[str, Any]:
    """What the client reads: the title, the analysis, the numbers as published. Nothing about who wrote or edited it."""
    return {"month": rep.period_month, "title": rep.title, "analysis": rep.analysis, "published_at": rep.published_at.isoformat() if rep.published_at else None, "data": rep.metrics_snapshot}
