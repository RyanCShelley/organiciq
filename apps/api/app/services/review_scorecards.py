"""The Monthly review's three scorecards: Visibility, Traffic and Conversions, and the one line that says the month.

Worked out when the page is read, from the review (already worked out, or kept when the month locked) and a few direct reads for what the
review does not hold: each channel's sessions this month and last, and the top conversions. Nothing here is stored, so a month that locked
before the scorecards existed gets them too. The one line is written by rules from the numbers, so it always agrees with the cards.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.config import ConversionDefinition
from app.models.ga4 import FactGa4Event, FactGa4Traffic, OrganicChannel
from app.models.seranking import FactSerRanking
from app.models.watchlist import WatchlistKeyword
from app.services.monthly_review import parse_month, pct_change, previous_month

#: A move under this many percent is "flat".
FLAT_PCT = 5.0
#: Channels named on the card, in the order shown. Everything else is "All other".
CHANNELS = (
    (OrganicChannel.ORGANIC_SEARCH, "Organic search"),
    (OrganicChannel.AI_REFERRAL, "AI referrals"),
    (OrganicChannel.DIRECT_UNATTRIBUTED, "Direct"),
    (OrganicChannel.REFERRAL, "Referral"),
)
TOP_CONVERSIONS = 3
#: How many months each card's trend line covers, ending with the month reviewed.
TREND_MONTHS = 6


def verdict(change_pct: float | None) -> str:
    """Up, down or flat for a percent change. Flat also covers a change that cannot be worked out."""
    if change_pct is None or abs(change_pct) < FLAT_PCT:
        return "flat"
    return "up" if change_pct > 0 else "down"


def _period(month: str, *, today: date | None = None) -> tuple[date, date]:
    """The month's days, as the review reads them: a month still running stops at yesterday."""
    today = today or date.today()
    first, last = parse_month(month)
    yesterday = today - timedelta(days=1)
    return first, (min(last, yesterday) if first <= yesterday else last)


def _channel_sessions(db: Session, client: Client, first: date, last: date) -> tuple[dict[str, float], float]:
    rows = (
        db.query(FactGa4Traffic.channel, func.coalesce(func.sum(FactGa4Traffic.sessions), 0))
        .filter(FactGa4Traffic.client_id == client.id, FactGa4Traffic.date >= first, FactGa4Traffic.date <= last)
        .group_by(FactGa4Traffic.channel)
        .all()
    )
    by = {(c.value if hasattr(c, "value") else str(c)): float(v or 0) for c, v in rows}
    return by, sum(by.values())


def traffic_mix(db: Session, client: Client, month: str) -> list[dict[str, Any]]:
    """Sessions by where the visit came from, this month against last. Channels with no visits in either month are left out."""
    now, now_total = _channel_sessions(db, client, *_period(month))
    then, then_total = _channel_sessions(db, client, *_period(previous_month(month)))
    out, named_now, named_then = [], 0.0, 0.0
    for channel, label in CHANNELS:
        a, b = now.get(channel.value, 0.0), then.get(channel.value, 0.0)
        named_now, named_then = named_now + a, named_then + b
        if a or b:
            out.append({"key": channel.value, "label": label, "sessions": round(a), "previous": round(b), "change_pct": pct_change(a, b)})
    other_now, other_then = max(now_total - named_now, 0.0), max(then_total - named_then, 0.0)
    if other_now or other_then:
        out.append({"key": "other", "label": "All other", "sessions": round(other_now), "previous": round(other_then), "change_pct": pct_change(other_now, other_then)})
    return out


def top_conversions(db: Session, client: Client, month: str) -> list[dict[str, Any]]:
    """The conversions people took most, by the name the team gave each: this month against last."""
    defs = {d.event_name: d.conversion_name for d in db.query(ConversionDefinition).filter(ConversionDefinition.client_id == client.id, ConversionDefinition.active.is_(True), ConversionDefinition.conversion_type == "lead")}
    if not defs:
        return []

    def counts(first: date, last: date) -> dict[str, float]:
        out: dict[str, float] = {}
        rows = (
            db.query(FactGa4Event.event_name, func.coalesce(func.sum(FactGa4Event.event_count), 0))
            .filter(FactGa4Event.client_id == client.id, FactGa4Event.date >= first, FactGa4Event.date <= last, FactGa4Event.event_name.in_(list(defs)))
            .group_by(FactGa4Event.event_name)
            .all()
        )
        for name, n in rows:
            out[defs[name]] = out.get(defs[name], 0.0) + float(n or 0)
        return out

    now, then = counts(*_period(month)), counts(*_period(previous_month(month)))
    rows = [{"label": name, "count": round(now.get(name, 0.0)), "previous": round(then.get(name, 0.0)), "change_pct": pct_change(now.get(name, 0.0), then.get(name, 0.0))} for name in {*now, *then}]
    rows.sort(key=lambda r: (-r["count"], -r["previous"], r["label"]))
    return rows[:TOP_CONVERSIONS]


def trend_months(month: str, n: int = TREND_MONTHS) -> list[str]:
    """The `n` months ending with `month`, oldest first."""
    out = [month]
    while len(out) < n:
        out.append(previous_month(out[-1]))
    return out[::-1]


def _series(months: list[str], by_month: dict[str, float]) -> list[dict[str, Any]]:
    """One point per month. A month with nothing recorded is None, not 0, so a client that began recently is not drawn as having collapsed."""
    return [{"month": m, "value": (round(by_month[m]) if m in by_month else None)} for m in months]


def _span(months: list[str]) -> tuple[date, date]:
    return parse_month(months[0])[0], _period(months[-1])[1]


def traffic_trend(db: Session, client: Client, months: list[str]) -> list[dict[str, Any]]:
    first, last = _span(months)
    key = func.to_char(FactGa4Traffic.date, "YYYY-MM")
    rows = db.query(key, func.coalesce(func.sum(FactGa4Traffic.sessions), 0)).filter(FactGa4Traffic.client_id == client.id, FactGa4Traffic.date >= first, FactGa4Traffic.date <= last).group_by(key).all()
    return _series(months, {m: float(v or 0) for m, v in rows})


def conversions_trend(db: Session, client: Client, months: list[str]) -> list[dict[str, Any]]:
    events = [d.event_name for d in db.query(ConversionDefinition).filter(ConversionDefinition.client_id == client.id, ConversionDefinition.active.is_(True), ConversionDefinition.conversion_type == "lead")]
    if not events:
        return _series(months, {})
    first, last = _span(months)
    key = func.to_char(FactGa4Event.date, "YYYY-MM")
    rows = db.query(key, func.coalesce(func.sum(FactGa4Event.event_count), 0)).filter(FactGa4Event.client_id == client.id, FactGa4Event.date >= first, FactGa4Event.date <= last, FactGa4Event.event_name.in_(events)).group_by(key).all()
    return _series(months, {m: float(v or 0) for m, v in rows})


def visibility_trend(db: Session, client: Client, months: list[str]) -> list[dict[str, Any]]:
    """The watchlist terms' Google impressions each month: the same measure as the card's impressions row."""
    from app.services.review_visibility import _google, key_of

    keys = sorted({key_of(k) for (k,) in db.query(WatchlistKeyword.keyword).filter(WatchlistKeyword.client_id == client.id)})
    if not keys:
        return _series(months, {})
    by_month: dict[str, float] = {}
    for m in months:
        first, last = _period(m)
        found = _google(db, client, keys, first, last)
        if found:
            by_month[m] = sum(v["impressions"] for v in found.values())
    return _series(months, by_month)


#: SE Ranking checks to this depth; a keyword it did not find reads 0 (or nothing).
RANK_DEPTH = 100
#: A keyword that fell at least this many places in the month is named as the biggest drop.
DROP_PLACES = 5


def rank_check(db: Session, client: Client, month: str) -> dict[str, Any] | None:
    """SE Ranking's daily position checks for the month: how many tracked keywords it found in Google's top 100 on the last check,
    how many in the top 10, the best one, and the biggest fall over the month. None when the client has no checks in the month."""
    first, last = _period(month)
    rows = (
        db.query(FactSerRanking.site_engine_id, FactSerRanking.keyword_id, FactSerRanking.keyword, FactSerRanking.date, FactSerRanking.position)
        .filter(FactSerRanking.client_id == client.id, FactSerRanking.date >= first, FactSerRanking.date <= last)
        .order_by(FactSerRanking.date)
        .all()
    )
    if not rows:
        return None
    series: dict[tuple[str, str], list[tuple[date, float | None, str]]] = {}
    for engine, kid, keyword, day, pos in rows:
        series.setdefault((engine, kid), []).append((day, float(pos) if pos is not None else None, keyword))
    found = lambda p: p is not None and 0 < p <= RANK_DEPTH  # noqa: E731
    checked_on = max(r[3] for r in rows)
    latest = {k: v[-1] for k, v in series.items()}
    ranked = [(pos, kw) for (_, pos, kw) in latest.values() if found(pos)]
    best = min(ranked, default=None)
    drops = []
    for v in series.values():
        known = [(d, p) for d, p, _ in v if found(p)]
        last_pos = v[-1][1]
        if known and found(last_pos) and last_pos - known[0][1] >= DROP_PLACES:
            drops.append((last_pos - known[0][1], v[-1][2], known[0][1], last_pos))
    worst = max(drops, default=None)
    return {
        "checked_on": checked_on.isoformat(), "tracked": len(series), "ranked": len(ranked), "top10": sum(1 for pos, _ in ranked if pos <= 10),
        "best": {"keyword": best[1], "position": round(best[0])} if best else None,
        "biggest_drop": {"keyword": worst[1], "from": round(worst[2]), "to": round(worst[3])} if worst else None,
    }


def _pair(p: dict | None) -> tuple[float | None, float | None, float | None]:
    p = p or {}
    return p.get("current"), p.get("previous"), p.get("change_pct")


def _terms_showing_before(vis: dict) -> int:
    return sum(1 for b in vis.get("buckets", []) for t in b.get("terms", []) if ((t.get("google") or {}).get("impressions") or {}).get("previous"))


def _terms_impressions_before(vis: dict) -> float | None:
    values = [((t.get("google") or {}).get("impressions") or {}).get("previous") for b in vis.get("buckets", []) for t in b.get("terms", [])]
    known = [v for v in values if v is not None]
    return float(sum(known)) if known else None


def build(db: Session, client: Client, review: dict) -> dict[str, Any]:
    month, noun = review["month"], review.get("noun", "conversions")
    months = trend_months(month)
    prior = previous_month(month)
    vis = review.get("visibility") or {}
    vs = vis.get("summary") or {}
    llm = vis.get("llm") or {}
    llm_sum = llm.get("summary") or {}

    # Visibility: the watchlist's terms in Google. Impressions are the terms' own, this month against last, not the whole site's.
    showing, terms = vs.get("showing_in_google"), vs.get("terms")
    imp_now = vs.get("google_impressions")
    imp_then = _terms_impressions_before(vis) if vis else None
    imp_pct = pct_change(imp_now, imp_then) if imp_now is not None and imp_then else None
    showing_before = _terms_showing_before(vis) if vis else None
    vis_change = imp_pct if imp_pct is not None else (None if not showing_before else pct_change(showing or 0, showing_before))
    visibility = {
        "available": bool(vis and terms),
        "headline": showing, "of": terms, "verdict": verdict(vis_change),
        "page_one": vs.get("on_page_one"), "bing": vs.get("showing_in_bing"),
        "has_bing": bool((vis.get("bing") or {}).get("has_data")),
        "impressions": {"current": imp_now, "previous": imp_then, "change_pct": imp_pct},
        "ai_mentions": (llm_sum.get("mentions") or {}).get("current") if llm else None,
        "ai_links": (llm_sum.get("citations") or {}).get("current") if llm else None,
        "ai_runs": llm.get("runs") if llm else None,
        "trend": visibility_trend(db, client, months) if vis and terms else [],
        "rank_check": rank_check(db, client, month),
    }

    # Traffic
    cur, prev, pct = _pair(review.get("sessions"))
    mix = traffic_mix(db, client, month)
    organic = next((c for c in mix if c["key"] == "organic_search"), None)
    traffic = {"headline": cur, "previous": prev, "change_pct": pct, "verdict": verdict(pct), "trend": traffic_trend(db, client, months), "channels": mix, "organic_change_pct": organic["change_pct"] if organic else (review.get("organic_sessions") or {}).get("change_pct")}

    # Conversions
    c_cur, c_prev, c_pct = _pair(review.get("conversions"))
    goal = review.get("goal") or {}
    rev = review.get("revenue") or {}
    revenue = rev.get("revenue") if rev.get("status") == "measured" else None
    conversions = {
        "noun": noun, "headline": c_cur, "previous": c_prev, "change_pct": c_pct, "verdict": verdict(c_pct),
        "goal": goal.get("period_goal"), "goal_progress_pct": goal.get("progress_pct"),
        "top": top_conversions(db, client, month), "trend": conversions_trend(db, client, months),
        "revenue": revenue, "conversion_rate": review.get("conversion_rate"),
    }
    return {"month": month, "previous_month": prior, "visibility": visibility, "traffic": traffic, "conversions": conversions,
            "headline": one_line(month, prior, visibility, traffic, conversions),
            "reads": section_reads(month, prior, visibility, traffic, conversions)}


_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


def month_name(month: str) -> str:
    return _MONTHS[int(month[5:7]) - 1]


def _move(word_up: str, word_down: str, pct: float | None) -> str | None:
    if pct is None or abs(pct) < FLAT_PCT:
        return None
    return f"{word_up if pct > 0 else word_down} {abs(round(pct))}%"


def one_line(month: str, prior: str, visibility: dict, traffic: dict, conversions: dict) -> str:
    """The month in plain sentences, from the numbers: what moved most, what held, where visibility stands."""
    against = month_name(prior)
    noun = str(conversions["noun"]).capitalize()
    parts: list[str] = []

    move = _move("rose", "fell", conversions["change_pct"])
    rev = conversions.get("revenue") or {}
    rev_move = _move("rose", "fell", rev.get("change_pct")) if rev else None
    if conversions["headline"] is None:
        pass
    elif move and rev_move and move.split()[0] == rev_move.split()[0]:
        parts.append(f"{noun} {move} and revenue {rev_move.split(' ', 1)[1]} against {against}.")
    elif move:
        parts.append(f"{noun} {move} against {against}" + (f", while revenue {rev_move}." if rev_move else "."))
    else:
        parts.append(f"{noun} held steady against {against}" + (f", while revenue {rev_move}." if rev_move else "."))

    s_move = _move("up", "down", traffic["change_pct"])
    o_move = _move("up", "down", traffic["organic_change_pct"])
    if traffic["headline"] is not None:
        head = "Traffic held" if not s_move else ("Traffic grew" if traffic["change_pct"] > 0 else "Traffic fell")
        pct = traffic["change_pct"]
        detail = f" (sessions {'up' if pct > 0 else 'down'} {abs(round(pct))}%)" if pct is not None and abs(round(pct)) >= 1 else ""
        tail = f" while organic search is {o_move}" if o_move else ""
        parts.append(f"{head}{detail}{tail}.")

    if visibility["available"]:
        v = visibility["verdict"]
        text = f"Visibility is {v}: {visibility['headline']} of {visibility['of']} terms show in Google"
        mentions, links = visibility.get("ai_mentions"), visibility.get("ai_links")
        if mentions is None:
            text += "."
        elif not mentions and not links:
            text += " and AI platforms do not name the brand yet."
        else:
            text += f" and AI platforms named the brand {round(mentions)} {'time' if round(mentions) == 1 else 'times'}."
        parts.append(text)
    return " ".join(parts)


def section_reads(month: str, prior: str, visibility: dict, traffic: dict, conversions: dict) -> dict[str, str | None]:
    """One or two plain sentences under each section's title: what its numbers say, so a focus can be chosen from the page."""
    against = month_name(prior)

    vis = None
    if visibility["available"]:
        shown, of = visibility["headline"] or 0, visibility["of"] or 0
        missing = of - shown
        if missing <= 0:
            vis = f"Every one of the {of} watchlist terms shows in Google."
        else:
            vis = f"{missing} of {of} watchlist terms never show in Google."
            page_one = visibility.get("page_one") or 0
            if shown:
                vis += " The terms that do show mostly sit on page one, so reach is the gap, not rank." if page_one * 2 >= shown else " The terms that do show mostly sit below page one, so rank is a gap as well as reach."

    tr = None
    mix = {c["key"]: c for c in traffic["channels"]}
    organic, ai = mix.get("organic_search"), mix.get("ai_referral")
    o_move, a_move = _move("up", "down", organic["change_pct"] if organic else None), _move("up", "down", ai["change_pct"] if ai else None)
    if o_move and a_move and o_move.split()[0] != a_move.split()[0]:
        tr = f"Organic is {o_move}, but AI referrals are {a_move}."
    elif o_move:
        tr = f"Organic search is {o_move} on {against}."
    elif traffic["headline"] is not None:
        tr = f"Organic search held steady on {against}."
    total = sum(c["sessions"] for c in traffic["channels"])
    direct = mix.get("direct_unattributed")
    if tr and direct and total and direct["sessions"] * 2 > total:
        tr += " Direct is more than half of all visits."

    conv = None
    noun = str(conversions["noun"])
    if conversions["headline"] is not None:
        move = _move("up", "down", conversions["change_pct"])
        pct = conversions.get("goal_progress_pct")
        if conversions.get("goal") and pct is not None:
            conv = f"{noun.capitalize()} are at {round(pct)}% of this period's goal" + (f", and {move} on {against}." if move else ".")
        elif move:
            conv = f"{noun.capitalize()} are {move} on {against}."
    return {"visibility": vis, "traffic": tr, "conversions": conv}
