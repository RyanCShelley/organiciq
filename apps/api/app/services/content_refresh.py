"""Content refreshes: the pages worth updating, ranked by the traffic that is at stake.

Each page with enough organic sessions is held against the whole site's own year-over-year change (the Decision engine's traffic tests in
`app.decisions.traffic_candidates`), so a page is "losing traffic" when it falls further than the site did, not when the whole market
dipped. A page is also stale when it has not been updated in a long time while it earns, and thin when it has few words. Where two pages
are shown for the same search, they are named as competing: the page that should be refreshed, or merged, is then a choice between them.

A lifecycle label from Topic Hub (winner, decaying, dead, healthy) becomes plain words here: Growing, Steady, Slipping, Losing traffic,
Gone quiet, New.

The page's depth score is Topic Hub's (`content_depth`), run on the page as it is today, so it is read on demand when a page is opened.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from lxml import html as lxml_html
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions import traffic_candidates as tc
from app.decisions import visibility_candidates as vc
from app.decisions.visibility_candidates import add_months
from app.models.annotation import Annotation
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.engine_task import EngineTask
from app.models.gsc import FactGscQueryPage
from app.models.schema_tools import ContentState
from app.services.content_depth import score_content_depth
from app.services.page_diagnostic import read_page

LIST_SIZE = 60
STALE_MONTHS = 18
THIN_WORDS = 300
GROWING_RATIO = 1.25
GONE_QUIET = 0.2
COMPETING_MIN_IMPRESSIONS = 30
COMPETING_SHARE = 0.25
COMPETING_MAX_POSITION = 30
COMPETING_SHOWN = 25
LOOKBACK_DAYS = 90
WINDOW_DAYS = 28

LABELS = {"growing": "Growing", "steady": "Steady", "slipping": "Slipping", "losing": "Losing traffic", "quiet": "Gone quiet", "new": "New"}


def _months_since(day: date | None, today: date) -> int | None:
    if day is None:
        return None
    return max(0, (today.year - day.year) * 12 + today.month - day.month)


def _label(m: dict[str, float], j: dict[str, Any], site_ratio: float | None, series: dict[str, float], cur3: list[str]) -> str:
    if m["ly3"] <= 0 and m["cur3"] > 0:
        return "new"
    if m["ly3"] >= tc.POSSIBLE_MIN_BASELINE and m["cur3"] <= GONE_QUIET * m["ly3"]:
        return "quiet"
    if j["sudden"] or j["slow_bleed"]:
        return "losing"
    if j["possible"]:
        return "slipping"
    retention = j["retention"]
    if retention is not None and retention >= GROWING_RATIO * (site_ratio if site_ratio is not None else 1.0) and m["cur3"] >= tc.PAGE_MIN_SESSIONS:
        return "growing"
    return "steady"


def _reasons(label: str, m: dict[str, float], j: dict[str, Any], site_ratio: float | None, age: int | None, words: int | None) -> list[str]:
    out = []
    if label in ("losing", "slipping", "quiet") and m["ly3"]:
        change = round((m["cur3"] / m["ly3"] - 1) * 100)
        site = f", while the whole site is {round((site_ratio - 1) * 100):+d}%" if site_ratio is not None else ""
        out.append(f"Organic sessions are {change:+d}% on the same three months last year{site}.")
    if j["sudden"] or (label in ("losing", "slipping") and j["soft_sudden"]):
        out.append(f"Last month it fell {round(j['drop'] * 100)}% against the month before.")
    if age is not None and age >= STALE_MONTHS:
        out.append(f"Last updated about {age} months ago.")
    if words is not None and 0 < words < THIN_WORDS:
        out.append(f"Only {words} words on the page.")
    return out


def _snapshots(db: Session, client: Client) -> dict[str, FactCrawlPageSnapshot]:
    return {
        s.normalized_url: s
        for s in db.query(FactCrawlPageSnapshot).filter(
            FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot.status_code == 200
        )
    }


def build(db: Session, client: Client, month: str, *, show_ignored: bool = False, q: str | None = None) -> dict[str, Any]:
    year, mon = int(month[:4]), int(month[5:7])
    month_start = date(year, mon, 1)
    cur, prev = tc._month_key(month_start), tc._month_key(add_months(month_start, -1))
    cur3 = tc._months_back(month_start, 3)
    ly3 = [tc._month_key(add_months(month_start, -(i + 12))) for i in range(3)]
    window_first = add_months(month_start, -14)
    window_last = add_months(month_start, 1).replace(day=1) - timedelta(days=1)
    today = date.today()

    pages = tc.monthly_sessions(db, client.id, window_first, window_last)
    site_series: dict[str, float] = defaultdict(float)
    for series in pages.values():
        for k, v in series.items():
            site_series[k] += v
    site = tc._measure(site_series, cur, prev, cur3, ly3)
    has_last_year = site["ly3"] > 0
    site_ratio = (site["cur3"] / site["ly3"]) if has_last_year else None

    snaps = _snapshots(db, client)
    set_aside = {k for (k,) in db.query(ContentState.key).filter(ContentState.client_id == client.id, ContentState.area == "refresh")}
    needle = " ".join((q or "").lower().split())

    rows: list[dict[str, Any]] = []
    for url, series in pages.items():
        m = tc._measure(series, cur, prev, cur3, ly3)
        snap = snaps.get(url)
        if needle:
            if needle not in url.lower() and needle not in ((snap.title if snap else None) or "").lower():
                continue
        elif max(m["cur3"], m["ly3"]) < tc.PAGE_MIN_SESSIONS:
            continue
        j = tc.judge(m, site_ratio)
        label = _label(m, j, site_ratio, series, cur3)
        age = _months_since(snap.content_updated_on, today) if snap else None
        words = snap.word_count if snap else None
        stale = age is not None and age >= STALE_MONTHS and m["cur3"] >= tc.PAGE_MIN_SESSIONS
        thin = words is not None and 0 < words < THIN_WORDS and m["cur3"] >= tc.PAGE_MIN_SESSIONS
        needs = label in ("losing", "slipping", "quiet") or stale or thin
        if not needs and not needle:
            continue
        at_stake = j["at_stake"]
        if label == "quiet":
            at_stake = max(at_stake, round((m["ly3"] - m["cur3"]) / 3, 1))
        rows.append(
            {
                "url": url, "title": snap.title if snap else None, "label": label, "status": LABELS[label],
                "sessions": {"current": round(m["current"]), "previous": round(m["previous"]), "change_pct": tc._pct(m["current"], m["previous"])},
                "three_months": {"current": round(m["cur3"]), "last_year": round(m["ly3"]), "change_pct": tc._pct(m["cur3"], m["ly3"])},
                "at_stake": round(at_stake), "last_updated": snap.content_updated_on.isoformat() if snap and snap.content_updated_on else None,
                "months_since_update": age, "words": words, "stale": stale, "thin": thin, "reasons": _reasons(label, m, j, site_ratio, age, words),
                "ignored": url in set_aside,
            }
        )
    live = [r for r in rows if not r["ignored"]]
    rows = [r for r in rows if r["ignored"] == show_ignored]
    order = {"losing": 0, "quiet": 1, "slipping": 2}
    rows.sort(key=lambda r: (order.get(r["label"], 3), -r["at_stake"], -r["three_months"]["current"]))

    return {
        "month": month, "q": needle or None, "showing_ignored": show_ignored, "has_last_year": has_last_year,
        "site": {"sessions": {"current": round(site["current"]), "previous": round(site["previous"])}, "three_months": {"current": round(site["cur3"]), "last_year": round(site["ly3"]), "change_pct": tc._pct(site["cur3"], site["ly3"])}},
        "counts": {
            "pages": len(live), "losing": sum(1 for r in live if r["label"] == "losing"), "quiet": sum(1 for r in live if r["label"] == "quiet"),
            "slipping": sum(1 for r in live if r["label"] == "slipping"), "stale": sum(1 for r in live if r["stale"]), "thin": sum(1 for r in live if r["thin"]),
            "at_stake": sum(r["at_stake"] for r in live),
        },
        "ignored_total": len(set_aside), "pages": rows[:LIST_SIZE], "pages_total": len(rows),
        "competing": competing(db, client),
        "notes": [
            "Organic search sessions by landing page, judged against the whole site's own change on the same three months last year.",
            ("Last year's months are missing from the data, so only sudden falls are caught." if not has_last_year else "At stake is the sessions a month the page has lost against what the site's own trend says it should have."),
            f"Stale means not updated in {STALE_MONTHS} months or more while it still earns sessions. Thin means under {THIN_WORDS} words.",
        ],
    }


def competing(db: Session, client: Client, today: date | None = None) -> list[dict[str, Any]]:
    """Searches two or more of the site's pages are shown for: one page may be taking the other's place, or they may be one page."""
    today = today or date.today()
    start = today - timedelta(days=LOOKBACK_DAYS)
    q = func.lower(func.trim(FactGscQueryPage.query))
    brand = vc.brand_keys(client)
    rows = (
        db.query(q, FactGscQueryPage.normalized_url, func.sum(FactGscQueryPage.impressions), func.sum(FactGscQueryPage.clicks), func.sum(FactGscQueryPage.average_position * FactGscQueryPage.impressions))
        .filter(FactGscQueryPage.client_id == client.id, FactGscQueryPage.date >= start, FactGscQueryPage.date <= today)
        .group_by(q, FactGscQueryPage.normalized_url)
        .all()
    )
    by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for query, url, imp, clk, weighted in rows:
        imp = float(imp or 0)
        if imp < COMPETING_MIN_IMPRESSIONS or not query or vc.is_brand(query, brand):
            continue
        position = float(weighted or 0) / imp
        if position > COMPETING_MAX_POSITION:
            continue
        by_query[query].append({"url": url, "impressions": round(imp), "clicks": round(float(clk or 0)), "position": round(position, 1)})
    out = []
    for query, shown in by_query.items():
        if len(shown) < 2:
            continue
        shown.sort(key=lambda r: -r["impressions"])
        if shown[1]["impressions"] < COMPETING_SHARE * shown[0]["impressions"]:
            continue
        out.append({"query": query, "impressions": sum(r["impressions"] for r in shown), "pages": shown[:4]})
    out.sort(key=lambda r: -r["impressions"])
    return out[:COMPETING_SHOWN]


def structured_text(body: str) -> str:
    """The page's words one block to a line, with list items marked, so the depth score can see lists and tables."""
    try:
        doc = lxml_html.fromstring(body)
    except Exception:  # noqa: BLE001 - unreadable markup is an empty page
        return ""
    for tag in ("script", "style", "nav", "header", "footer", "aside", "noscript", "form"):
        for node in doc.xpath(f"//{tag}"):
            if node.getparent() is not None:
                node.getparent().remove(node)
    lines = []
    for node in doc.xpath("//h1|//h2|//h3|//h4|//p|//li|//tr|//blockquote"):
        text = " ".join(node.text_content().split())
        if not text:
            continue
        if node.tag == "li":
            lines.append(f"- {text}")
        elif node.tag == "tr":
            lines.append("| " + " | ".join(" ".join(c.text_content().split()) for c in node.xpath("./td|./th")) + " |")
        else:
            lines.append(text)
    return "\n".join(lines)


def _clicks_between(db: Session, client: Client, url: str, start: date, end: date) -> dict[str, Any] | None:
    imp, clk = db.query(func.coalesce(func.sum(FactGscQueryPage.impressions), 0), func.coalesce(func.sum(FactGscQueryPage.clicks), 0)).filter(
        FactGscQueryPage.client_id == client.id, FactGscQueryPage.normalized_url == url, FactGscQueryPage.date >= start, FactGscQueryPage.date <= end).one()
    if float(imp) < 30:
        return None
    return {"impressions": round(float(imp)), "clicks": round(float(clk))}


def changes_for(db: Session, client: Client, url: str, today: date | None = None) -> list[dict[str, Any]]:
    """Work done on this page (a shipped task, a change-log note), with its Search Console clicks in the 28 days before against the 28 days after."""
    today = today or date.today()
    events: list[tuple[date, str, str]] = []
    for t in db.query(EngineTask).filter(EngineTask.client_id == client.id, EngineTask.page_url == url, EngineTask.status == "shipped", EngineTask.shipped_at.isnot(None)):
        events.append((t.shipped_at.date(), "Shipped", t.title))
    for a in db.query(Annotation).filter(Annotation.client_id == client.id, Annotation.page_url == url, Annotation.engine_uid.is_(None)):
        events.append((a.date, "Noted", a.description))
    out = []
    for day, kind, text in sorted(events, reverse=True)[:6]:
        ready = day + timedelta(days=WINDOW_DAYS) <= today
        out.append(
            {
                "date": day.isoformat(), "kind": kind, "text": text,
                "before": _clicks_between(db, client, url, day - timedelta(days=WINDOW_DAYS), day - timedelta(days=1)),
                "after": _clicks_between(db, client, url, day + timedelta(days=1), day + timedelta(days=WINDOW_DAYS)) if ready else None,
                "measured_on": None if ready else (day + timedelta(days=WINDOW_DAYS)).isoformat(),
            }
        )
    return out


def page_detail(db: Session, client: Client, month: str, url: str) -> dict[str, Any]:
    """One page opened: its sessions by month, the searches it lost, the pages it competes with, what was done to it, and its depth score."""
    year, mon = int(month[:4]), int(month[5:7])
    month_start = date(year, mon, 1)
    window_last = add_months(month_start, 1).replace(day=1) - timedelta(days=1)
    series = tc.monthly_sessions(db, client.id, add_months(month_start, -14), window_last).get(url, {})
    months = [tc._month_key(add_months(month_start, -i)) for i in range(14, -1, -1)]
    snap = _snapshots(db, client).get(url)
    depth = None
    read = {"ok": False, "note": None}
    try:
        found = read_page(url, client.domain)
        if 200 <= found.status < 300 and found.body:
            result = score_content_depth(structured_text(found.body))
            depth = {"score": result.score, "signals": result.signals}
            read["ok"] = True
        else:
            read["note"] = f"The page answered {found.status}, so its words were not read."
    except Exception as exc:  # noqa: BLE001 - the rest of the detail stands without the live read
        read["note"] = str(exc)[:200]
    return {
        "url": url, "title": snap.title if snap else None, "words": snap.word_count if snap else None,
        "last_updated": snap.content_updated_on.isoformat() if snap and snap.content_updated_on else None,
        "sessions": [{"month": m, "sessions": round(series.get(m, 0))} for m in months],
        "lost": tc.queries_lost(db, client, month, url, limit=8),
        "competing": [c for c in competing(db, client) if any(p["url"] == url for p in c["pages"])][:6],
        "changes": changes_for(db, client, url), "depth": depth, "read": read,
    }
