"""The executive summary's numbers: a leadership view of search and AI visibility.

Headline figures, Google clicks by month (this year over last), the client against its competitors, and visibility by topic, Google beside AI answers.
Everything comes from Organic IQ's own data and is labelled: the client's tracked keyword topics, Search Console, the SE Ranking rank tracker and competitor
visibility, and the AI platform checks. Nothing is estimated to fill a gap: a figure with no source is None and says so.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.visibility_candidates import brand_keys, is_brand
from app.llm_visibility import report as llm_report
from app.models.client import Client
from app.models.consulting import ConsultingRecommendation
from app.models.gsc import FactGscDaily, FactGscQueryPage
from app.models.llm_visibility import ClientLlmSettings
from app.models.seranking import FactSerCompetitor, FactSerRanking, FactSerSiteSummary
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services import consulting_performance as cp
from app.services import monthly_review, review_visibility
from app.services.schema_pages import key_of

#: A topic reads green, amber or red. Google: the share of the topic's search demand where a tracked keyword is in the top 10. AI: the share of answers that name the brand.
GOOGLE_GREEN, GOOGLE_AMBER = 3.0, 0.5
AI_GREEN, AI_AMBER = 30.0, 10.0
CLICK_MONTHS = 13
VENDORS_SHOWN = 10
PRIORITIES_SHOWN = 5


def _heat(value: float | None, green: float, amber: float) -> str | None:
    if value is None:
        return None
    return "green" if value >= green else "amber" if value >= amber else "red"


def _gsc_clicks(db: Session, client: Client, month: str) -> float | None:
    a, b = cp._month_bounds(month)
    v = db.query(func.sum(FactGscDaily.clicks)).filter(FactGscDaily.client_id == client.id, FactGscDaily.date >= a, FactGscDaily.date <= b).scalar()
    return float(v) if v else None


def _clicks_by_month(db: Session, client: Client, month: str) -> list[dict[str, Any]]:
    return [{"month": m, "value": _gsc_clicks(db, client, m)} for m in (cp._shift(month, -i) for i in range(CLICK_MONTHS - 1, -1, -1))]


def _site_visibility(db: Session, client: Client, month: str) -> float | None:
    a, b = cp._month_bounds(month)
    row = db.query(FactSerSiteSummary).filter(FactSerSiteSummary.client_id == client.id, FactSerSiteSummary.metric_date >= a, FactSerSiteSummary.metric_date <= b).order_by(FactSerSiteSummary.metric_date.desc()).first()
    return float(row.visibility_percent) if row and row.visibility_percent is not None else None


def _competitor_visibility(db: Session, client: Client, month: str) -> dict[str, dict[str, Any]]:
    """Each competitor's latest SE Ranking visibility up to the end of the month.

    SE Ranking keeps one row per competitor (the latest pull), so there is no
    history to compare against: a competitor shows its current level only.
    """
    _, b = cp._month_bounds(month)
    rows = db.query(FactSerCompetitor).filter(FactSerCompetitor.client_id == client.id, FactSerCompetitor.metric_date <= b, FactSerCompetitor.visibility.isnot(None)).order_by(FactSerCompetitor.metric_date.desc(), FactSerCompetitor.updated_at.desc()).all()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        out.setdefault(r.competitor_id, {"name": (r.name or r.url or r.competitor_id), "visibility": float(r.visibility)})
    return out


def _brand(db: Session, client: Client) -> str:
    return (db.query(ClientLlmSettings.brand_name).filter(ClientLlmSettings.client_id == client.id).scalar() or client.client_name or "").strip()


def _named(r: Any) -> bool:
    return bool(r.brand_mentioned or r.url_cited)


def _vendor_shares(rows: list[Any], brand: str) -> list[dict[str, Any]]:
    valid = llm_report._valid(rows)
    if not valid:
        return []
    counts: Counter[str] = Counter()
    for r in valid:
        if _named(r):
            counts[brand] += 1
        for name in set(r.competitors_mentioned or []):
            counts[name] += 1
    total = len(valid)
    out = [{"name": n, "share_pct": round(c / total * 100, 1), "is_self": n == brand} for n, c in counts.items()]
    if brand not in counts:
        out.append({"name": brand, "share_pct": 0.0, "is_self": True})
    out.sort(key=lambda r: (-r["share_pct"], r["name"]))
    return out


def _topic_rows(db: Session, client: Client, month: str, llm_rows: list[Any], brand: str) -> list[dict[str, Any]]:
    a, b = cp._month_bounds(month)
    last_day = db.query(func.max(FactSerRanking.date)).filter(FactSerRanking.client_id == client.id, FactSerRanking.date >= a, FactSerRanking.date <= b).scalar()
    positions: dict[str, tuple[float, float | None]] = {}
    if last_day is not None:
        for kw, pos, vol in db.query(FactSerRanking.keyword, FactSerRanking.position, FactSerRanking.volume).filter(FactSerRanking.client_id == client.id, FactSerRanking.date == last_day):
            positions[key_of(kw)] = (float(pos or 0), float(vol) if vol is not None else None)
    bkeys = brand_keys(client)
    ya_a, ya_b = cp._month_bounds(cp._shift(month, -12))

    def clicks(keys: list[str], first: date, last: date) -> float | None:
        if not keys:
            return None
        q = func.lower(func.trim(FactGscQueryPage.query))
        rows = db.query(q, func.sum(FactGscQueryPage.clicks)).filter(FactGscQueryPage.client_id == client.id, FactGscQueryPage.date >= first, FactGscQueryPage.date <= last, q.in_(keys)).group_by(q).all()
        total = sum(float(c or 0) for k, c in rows if not is_brand(k, bkeys))
        return total if rows else None

    valid = llm_report._valid(llm_rows)
    out = []
    buckets = db.query(WatchlistBucket).filter(WatchlistBucket.client_id == client.id).order_by(WatchlistBucket.sort_order, WatchlistBucket.name).all()
    for bucket in buckets:
        terms = db.query(WatchlistKeyword).filter(WatchlistKeyword.client_id == client.id, WatchlistKeyword.bucket_id == bucket.id).all()
        if not terms:
            continue
        keys = [key_of(t.keyword) for t in terms]
        volume = lambda t: float(t.volume) if t.volume is not None else (positions.get(key_of(t.keyword), (0, None))[1] or 0.0)  # noqa: E731
        demand = sum(volume(t) for t in terms)
        in_top10 = sum(volume(t) for t in terms if 0 < positions.get(key_of(t.keyword), (0, None))[0] <= 10)
        top10 = round(in_top10 / demand * 100, 1) if demand and positions else None
        prompts = {key_of(t.paired_ai_prompt) for t in terms if t.paired_ai_prompt}
        mine = [r for r in valid if key_of(r.query_text) in prompts]
        ai_share, leader = None, None
        if mine:
            shares = _vendor_shares(mine, brand)
            me = next((v for v in shares if v["is_self"]), {"share_pct": 0.0})
            ai_share = me["share_pct"]
            top = shares[0] if shares else None
            leader = {"name": top["name"], "share_pct": top["share_pct"], "is_self": top["is_self"]} if top else None
        now, then = clicks(keys, a, b), clicks(keys, ya_a, ya_b)
        row = {
            "name": bucket.name, "keywords": len(terms), "searches_per_month": round(demand) if demand else None,
            "google_top10_pct": top10, "google_heat": _heat(top10, GOOGLE_GREEN, GOOGLE_AMBER),
            "ai_share_pct": ai_share, "ai_heat": _heat(ai_share, AI_GREEN, AI_AMBER), "ai_leader": leader,
            "ai_overview_pct": None,  # shown only where SE Ranking's AI tracker holds it
            "clicks": {"value": now, "last_year": then, "change": round(now - then) if now is not None and then is not None else None},
        }
        row["read_out"] = _read_out(row)
        out.append(row)
    return out


def _read_out(t: dict[str, Any]) -> str:
    g, a = t["google_heat"], t["ai_heat"]
    leader = t["ai_leader"]
    lead = f" {leader['name']} appears in {round(leader['share_pct'])}% of AI answers." if leader and not leader["is_self"] else ""
    if g is None and a is None:
        return "Not measured yet: no rank check or AI answers cover this topic."
    if g == "green" and a == "green":
        return "Strong in Google and in AI answers."
    if a == "green":
        return "Visible in AI answers, but organic rankings trail."
    if g == "green":
        return "Ranks well in Google, but AI answers seldom name you." + lead
    if g == "red" and a == "red":
        return "A gap in both Google and AI answers." + lead
    if a == "red":
        return "Present in Google, nearly absent from AI answers." + lead
    return "Present, with room to grow." + lead


def build(db: Session, client: Client, month: str) -> dict[str, Any]:
    monthly_review.parse_month(month)
    prev3 = cp._shift(month, -3)
    brand = _brand(db, client)
    llm = review_visibility._llm(db, client, month)
    llm_rows = llm["_rows"] if llm else []

    clicks_series = _clicks_by_month(db, client, month)
    now_clicks, ly_clicks, prev_clicks = clicks_series[-1]["value"], _gsc_clicks(db, client, cp._shift(month, -12)), clicks_series[-2]["value"]
    vendors = _vendor_shares(llm_rows, brand)
    topics = _topic_rows(db, client, month, llm_rows, brand)

    ours_now, ours_then = _site_visibility(db, client, month), _site_visibility(db, client, prev3)
    comp_now = _competitor_visibility(db, client, month)
    shares = {v["name"]: v["share_pct"] for v in vendors}
    competitors = []
    for cid, c in comp_now.items():
        competitors.append({"name": c["name"], "is_self": False, "visibility": c["visibility"], "change_pct": None, "ai_share_pct": shares.get(c["name"])})
    competitors.sort(key=lambda r: -r["visibility"])
    if ours_now is not None:
        competitors.insert(0, {"name": brand, "is_self": True, "visibility": ours_now, "change_pct": cp._pct(ours_now, ours_then), "ai_share_pct": shares.get(brand)})
    peers = [c["visibility"] for c in competitors if not c["is_self"]]
    me = next((c for c in competitors if c["is_self"]), None)

    rank = next((i + 1 for i, v in enumerate(vendors) if v["is_self"]), None)
    scored = [t for t in topics if t["ai_share_pct"] is not None]
    best = max(scored, key=lambda t: t["ai_share_pct"], default=None)
    worst = min(scored, key=lambda t: t["ai_share_pct"], default=None)

    kpis = [
        {"label": f"Google clicks, {_month_label(month)}", "value": now_clicks, "unit": "", "sub": _clicks_sub(now_clicks, ly_clicks, prev_clicks, month), "tone": _tone(cp._pct(now_clicks, ly_clicks))},
        {"label": "Google visibility vs peers", "value": me["visibility"] if me else None, "unit": "%", "sub": " ".join(x for x in ((f"{me['change_pct']:+.0f}% over three months." if me and me["change_pct"] is not None else ""), (f"{len(peers)} peers sit at {min(peers):.0f}% to {max(peers):.0f}%." if peers else "No competitor visibility is tracked yet.")) if x), "tone": _tone(me["change_pct"] if me else None)},
        {"label": "AI share of voice", "value": next((v["share_pct"] for v in vendors if v["is_self"]), None), "unit": "%", "sub": (f"#{rank} of {len(vendors)} vendors named in AI answers" if rank else "No AI check has finished for this month."), "tone": _tone(None)},
        {"label": "Strongest topic", "value": best["name"] if best else None, "unit": "", "sub": (f"{round(best['ai_share_pct'])}% AI share of voice." + (f" Biggest gap: {worst['name']} ({round(worst['ai_share_pct'])}%)." if worst and worst is not best else "")) if best else "No topic has AI answers yet.", "tone": _tone(None)},
    ]
    recs = db.query(ConsultingRecommendation).filter(ConsultingRecommendation.client_id == client.id, ConsultingRecommendation.review_state == "published").all()
    order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: (order.get(r.priority, 3), -(r.published_at.timestamp() if r.published_at else 0)))
    run_dates = llm["run_dates"] if llm else []
    return {
        "month": month, "brand": brand, "kpis": kpis, "clicks_by_month": clicks_series, "clicks_year_ago_month": cp._shift(month, -12),
        "competitors": competitors, "topics": topics, "ai_vendors": vendors[:VENDORS_SHOWN], "ai_runs": llm["runs"] if llm else 0, "ai_run_dates": run_dates,
        "priorities": [{"title": r.title, "action": r.action} for r in recs[:PRIORITIES_SHOWN]],
        "about": [
            f"Google clicks: Search Console, {client.domain}, {_month_label(month)} against the same month a year earlier.",
            "Topics: the keywords tracked for this site, grouped as set up in Organic IQ. Clicks are from those tracked terms with brand queries left out.",
            "Google top-10 share of demand: the share of a topic's monthly searches where a tracked keyword ranks in Google's top 10 on the last rank check of the month. It covers tracked keywords, not all demand.",
            f"AI share of voice: the share of AI answers to the questions asked on each topic that name or link to each vendor, sampled from {len(run_dates)} check{'s' if len(run_dates) != 1 else ''}{f' (latest {run_dates[-1]})' if run_dates else ''}. Figures do not add up to 100% because an answer can name several vendors.",
            "Visibility: SE Ranking's visibility score for this site (three-month change) and the latest score for each tracked competitor. Competitor history is not kept, so only their current level is shown. These are estimates, not analytics.",
        ],
        "sources": ["Search Console", "SE Ranking", "AI platform checks"],
    }


def _month_label(month: str) -> str:
    return date(int(month[:4]), int(month[5:7]), 1).strftime("%b %Y")


def _tone(pct: float | None) -> str:
    return "neutral" if pct is None or abs(pct) < 1 else "good" if pct > 0 else "bad"


def _clicks_sub(now: float | None, ly: float | None, prev: float | None, month: str) -> str:
    parts = []
    c = cp._pct(now, ly)
    if c is not None:
        parts.append(f"{c:+.0f}% vs {_month_label(cp._shift(month, -12))}")
    p = cp._pct(now, prev)
    if p is not None:
        parts.append(f"{p:+.0f}% vs {_month_label(cp._shift(month, -1))}")
    return " · ".join(parts) or "No Search Console data for this month."
