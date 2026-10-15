"""Find the demand a site is shown for and has no page about.

`content_gap_signals` starts from the terms somebody tracks. On most clients
that is a short list chosen at setup, so a gap analysis confined to it can only
ever say "the pages you thought of exist". This starts from Search Console:
every query the site's results were shown for, minus what is tracked, mapped,
the brand itself, already earning, or already answered by a page.

What is left is demand with no page about it. It still needs a price — volume
and difficulty — before it can be prescribed, because a query the site was
shown for twice and a query thousands search are not the same slot of a
retainer. Pricing is bought for the few largest, monthly, and stored.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date, timedelta
from urllib.parse import urlsplit

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.content_gaps import (
    COVERED_SHARE,
    EARNING_POSITION,
    MIN_DEMAND_IMPRESSIONS,
    MIN_VOLUME,
    DemandGap,
    NearPage,
    content_words,
    fold_variants,
)
from app.models.client import Client
from app.models.crawl import FactCrawlPageSnapshot
from app.models.decision import KeywordTarget
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerCompetitorKeyword, FactSerKeyword, FactSerKeywordMetric
from app.services.content_gap_signals import MIN_CRAWLED_PAGES, NEAREST_PAGES, GapScan
from app.services.page_signals import brand_terms, is_navigational

#: Three months of queries. A month of Search Console is too thin for a small
#: site's long tail; a year would include demand that has gone.
LOOKBACK_DAYS = 90

#: Queries bought a price each month, per client. SE Ranking bills per keyword
#: looked up, so this is the ceiling on what the analysis can spend.
PRICING_LIMIT = 25


def _load_site(
    db: Session, client: Client
) -> tuple[dict, dict[str, frozenset[str]], frozenset[str]] | str:
    """The indexable pages and the words each is about, or why there is no site to read."""
    pages = {
        row.normalized_url: row
        for row in db.query(FactCrawlPageSnapshot).filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.indexable.is_(True),
        )
    }
    if len(pages) < MIN_CRAWLED_PAGES:
        return (
            f"The crawl found {len(pages)} indexable "
            f"page{'' if len(pages) == 1 else 's'}, too few to say a query has no "
            "page. Fix the crawl before looking for demand."
        )
    page_words: dict[str, frozenset[str]] = {}
    for url, row in pages.items():
        headings = [
            str(s.get("heading") or "") for s in (row.sections or []) if isinstance(s, dict)
        ]
        page_words[url] = content_words(" ".join([row.title or "", urlsplit(url).path, *headings]))
    return pages, page_words, frozenset().union(*page_words.values())


def demand_candidates(
    db: Session, client: Client, *, today: date | None = None
) -> tuple[list[DemandGap], dict[str, int], str | None]:
    """Unpriced demand gaps, largest first, with the counts behind them.

    The third value is set when the scan cannot say anything: a crawl that
    saw too few pages cannot show that a query has no page.
    """
    today = today or date.today()
    start = today - timedelta(days=LOOKBACK_DAYS)

    site = _load_site(db, client)
    if isinstance(site, str):
        return [], {}, site
    pages, page_words, everywhere = site

    rows = (
        db.query(
            func.lower(func.trim(FactGscQueryPage.query)),
            FactGscQueryPage.normalized_url,
            func.sum(FactGscQueryPage.impressions),
            func.sum(FactGscQueryPage.clicks),
            func.sum(FactGscQueryPage.impressions * FactGscQueryPage.average_position),
        )
        .filter(
            FactGscQueryPage.client_id == client.id,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= today,
        )
        .group_by(func.lower(func.trim(FactGscQueryPage.query)), FactGscQueryPage.normalized_url)
        .all()
    )
    by_query: dict[str, list[tuple[str, float, float, float]]] = defaultdict(list)
    for query, url, impressions, clicks, weighted_position in rows:
        if query and url:
            by_query[query].append(
                (url, float(impressions or 0), float(clicks or 0), float(weighted_position or 0))
            )

    tracked = {
        (row[0] or "").strip().lower()
        for row in db.query(FactSerKeyword.keyword).filter(FactSerKeyword.client_id == client.id)
    }
    targeted = {
        (row[0] or "").strip().lower()
        for row in db.query(KeywordTarget.keyword).filter(KeywordTarget.client_id == client.id)
    }
    brand = brand_terms(client)

    summary = {
        "demand_queries": len(by_query),
        "demand_tracked": 0,
        "demand_brand": 0,
        "demand_small": 0,
        "demand_earning": 0,
        "demand_covered": 0,
    }
    gaps: list[DemandGap] = []
    for query, shown in by_query.items():
        if query in tracked or query in targeted:
            summary["demand_tracked"] += 1
            continue
        if is_navigational(query, brand):
            summary["demand_brand"] += 1
            continue
        impressions = sum(item[1] for item in shown)
        if impressions < MIN_DEMAND_IMPRESSIONS:
            summary["demand_small"] += 1
            continue
        clicks = sum(item[2] for item in shown)
        position = sum(item[3] for item in shown) / impressions if impressions else None
        stand_in = max(shown, key=lambda item: item[1])
        stand_in_position = stand_in[3] / stand_in[1] if stand_in[1] else None
        if stand_in_position is not None and 0 < stand_in_position <= EARNING_POSITION:
            summary["demand_earning"] += 1
            continue

        words = content_words(query)
        if not words:
            continue
        absent = tuple(sorted(words - everywhere))
        best = max(len(words & pw) / len(words) for pw in page_words.values())
        if not absent and best >= COVERED_SHARE:
            # A page is about it and ranks badly: that is a refresh, which the
            # update pool already finds. Not a page to write.
            summary["demand_covered"] += 1
            continue

        nearest = sorted(
            ((len(words & pw), url) for url, pw in page_words.items() if words & pw),
            key=lambda pair: (-pair[0], pair[1]),
        )[:NEAREST_PAGES]
        gaps.append(
            DemandGap(
                term=query,
                impressions=impressions,
                clicks=clicks,
                position=position,
                stand_in_url=stand_in[0] if stand_in[0] in pages else None,
                nearest=tuple(
                    NearPage(
                        url=url,
                        title=pages[url].title,
                        shared=tuple(sorted(words & page_words[url])),
                    )
                    for _, url in nearest
                ),
                pages_searched=len(pages),
                absent_words=absent,
                best_overlap=best,
                lookback_days=LOOKBACK_DAYS,
            )
        )

    return fold_variants(gaps), summary, None


def _competitor_rows(db: Session, client: Client) -> dict[str, dict]:
    """What the competitors rank in the top ten for, one entry per query.

    Volume and difficulty are SE Ranking's own, from the same request that
    named the term; the largest volume reported wins when competitors differ.
    """
    found: dict[str, dict] = {}
    for row in db.query(FactSerCompetitorKeyword).filter(
        FactSerCompetitorKeyword.client_id == client.id
    ):
        term = (row.keyword or "").strip().lower()
        if not term or row.position is None:
            continue
        entry = found.setdefault(
            term, {"volume": None, "difficulty": None, "intents": (), "rivals": {}}
        )
        entry["rivals"][row.competitor_domain] = min(
            float(row.position), entry["rivals"].get(row.competitor_domain, 101.0)
        )
        if row.volume is not None and (
            entry["volume"] is None or float(row.volume) > entry["volume"]
        ):
            entry["volume"] = float(row.volume)
            entry["difficulty"] = float(row.difficulty) if row.difficulty is not None else None
    return found


def _rival_brand_terms(domains: set[str]) -> set[str]:
    terms: set[str] = set()
    for domain in domains:
        terms.add(domain)
        bare = domain.split(".")[0]
        if len(bare) > 3:
            terms.add(bare)
    return terms


def competitor_candidates(
    db: Session,
    client: Client,
    *,
    skip: set[str],
    today: date | None = None,
) -> tuple[list[DemandGap], dict[str, int]]:
    """Terms the closest competitors rank for that the site has no page about.

    Set aside, as for Search Console demand: what is tracked or mapped, the
    site's own brand, a rival's brand ("keysearch vs semrush" is about them),
    terms the site already holds a top-ten position for, and terms a page is
    already about. `skip` is the queries the Search Console scan has handled.
    """
    today = today or date.today()
    summary = {
        "competitor_keywords": 0,
        "competitor_tracked": 0,
        "competitor_brand": 0,
        "competitor_small": 0,
        "competitor_earning": 0,
        "competitor_covered": 0,
        "competitor_gaps": 0,
    }
    ranked = _competitor_rows(db, client)
    summary["competitor_keywords"] = len(ranked)
    if not ranked:
        return [], summary
    site = _load_site(db, client)
    if isinstance(site, str):
        return [], summary
    pages, page_words, everywhere = site

    tracked = {
        (row[0] or "").strip().lower()
        for row in db.query(FactSerKeyword.keyword).filter(FactSerKeyword.client_id == client.id)
    } | {
        (row[0] or "").strip().lower()
        for row in db.query(KeywordTarget.keyword).filter(KeywordTarget.client_id == client.id)
    }
    brand = brand_terms(client)
    rival_brand = _rival_brand_terms(
        {domain for entry in ranked.values() for domain in entry["rivals"]}
    )

    start = today - timedelta(days=LOOKBACK_DAYS)
    shown: dict[str, list[tuple[str, float, float, float]]] = defaultdict(list)
    candidates = [t for t in ranked if t not in skip]
    for offset in range(0, len(candidates), 500):
        chunk = candidates[offset : offset + 500]
        for query, url, impressions, clicks, weighted in (
            db.query(
                func.lower(func.trim(FactGscQueryPage.query)),
                FactGscQueryPage.normalized_url,
                func.sum(FactGscQueryPage.impressions),
                func.sum(FactGscQueryPage.clicks),
                func.sum(FactGscQueryPage.impressions * FactGscQueryPage.average_position),
            )
            .filter(
                FactGscQueryPage.client_id == client.id,
                FactGscQueryPage.date >= start,
                FactGscQueryPage.date <= today,
                func.lower(func.trim(FactGscQueryPage.query)).in_(chunk),
            )
            .group_by(
                func.lower(func.trim(FactGscQueryPage.query)), FactGscQueryPage.normalized_url
            )
        ):
            shown[query].append(
                (url, float(impressions or 0), float(clicks or 0), float(weighted or 0))
            )

    gaps: list[DemandGap] = []
    for term in candidates:
        entry = ranked[term]
        if term in tracked:
            summary["competitor_tracked"] += 1
            continue
        if is_navigational(term, brand) or is_navigational(term, rival_brand):
            summary["competitor_brand"] += 1
            continue
        volume, difficulty = entry["volume"], entry["difficulty"]
        if volume is None or difficulty is None or volume < MIN_VOLUME:
            summary["competitor_small"] += 1
            continue

        seen = shown.get(term, [])
        impressions = sum(item[1] for item in seen)
        clicks = sum(item[2] for item in seen)
        position = sum(item[3] for item in seen) / impressions if impressions else None
        stand_in = max(seen, key=lambda item: item[1]) if seen else None
        stand_in_position = stand_in[3] / stand_in[1] if stand_in and stand_in[1] else None
        if stand_in_position is not None and 0 < stand_in_position <= EARNING_POSITION:
            summary["competitor_earning"] += 1
            continue

        words = content_words(term)
        if not words:
            continue
        absent = tuple(sorted(words - everywhere))
        best = max(len(words & pw) / len(words) for pw in page_words.values())
        if not absent and best >= COVERED_SHARE:
            summary["competitor_covered"] += 1
            continue

        nearest = sorted(
            ((len(words & pw), url) for url, pw in page_words.items() if words & pw),
            key=lambda pair: (-pair[0], pair[1]),
        )[:NEAREST_PAGES]
        gaps.append(
            DemandGap(
                term=term,
                impressions=impressions,
                clicks=clicks,
                position=position,
                stand_in_url=stand_in[0] if stand_in and stand_in[0] in pages else None,
                volume=volume,
                difficulty=difficulty,
                nearest=tuple(
                    NearPage(
                        url=url,
                        title=pages[url].title,
                        shared=tuple(sorted(words & page_words[url])),
                    )
                    for _, url in nearest
                ),
                pages_searched=len(pages),
                absent_words=absent,
                best_overlap=best,
                lookback_days=LOOKBACK_DAYS,
                competitors=tuple(
                    sorted(entry["rivals"].items(), key=lambda pair: (pair[1], pair[0]))
                ),
            )
        )
    summary["competitor_gaps"] = len(gaps)
    return gaps, summary


def queries_to_price(db: Session, client: Client, *, today: date | None = None) -> list[str]:
    """The largest demand gaps with no price yet: what the pricing job buys.

    Already-priced terms are skipped here and in the job, so a term is paid
    for once however many months it stays a gap. A term a competitor ranks for
    arrived with its price, and is not bought again.
    """
    gaps, _, blocked = demand_candidates(db, client, today=today)
    if blocked or not gaps:
        return []
    priced = {
        (row[0] or "").strip().lower()
        for row in db.query(FactSerKeywordMetric.keyword).filter(
            FactSerKeywordMetric.client_id == client.id
        )
    }
    priced |= {
        term
        for term, entry in _competitor_rows(db, client).items()
        if entry["volume"] is not None and entry["difficulty"] is not None
    }
    return [g.term for g in gaps if g.term not in priced][:PRICING_LIMIT]


def scan_demand_gaps(db: Session, client: Client, *, today: date | None = None) -> GapScan:
    """Demand gaps with prices: Search Console's, and the competitors' beyond them."""
    gaps, summary, blocked = demand_candidates(db, client, today=today)
    if blocked:
        return GapScan(gaps=[], blocked=blocked)

    prices = {
        (row.keyword or "").strip().lower(): row
        for row in db.query(FactSerKeywordMetric).filter(
            FactSerKeywordMetric.client_id == client.id
        )
    }
    rivals = _competitor_rows(db, client)

    priced: list[DemandGap] = []
    unpriced = 0
    for gap in gaps:
        row = prices.get(gap.term)
        rival = rivals.get(gap.term)
        if row is not None and row.difficulty is not None and row.volume:
            found = replace(
                gap,
                volume=float(row.volume),
                difficulty=float(row.difficulty),
                intents=tuple(row.intents or ()),
            )
        elif rival is not None and rival["volume"] and rival["difficulty"] is not None:
            found = replace(gap, volume=rival["volume"], difficulty=rival["difficulty"])
        else:
            unpriced += 1
            continue
        if rival is not None:
            found = replace(
                found,
                competitors=tuple(
                    sorted(rival["rivals"].items(), key=lambda pair: (pair[1], pair[0]))
                ),
            )
        priced.append(found)

    from_competitors, competitor_summary = competitor_candidates(
        db, client, skip={g.term for g in gaps}, today=today
    )
    summary.update(competitor_summary)
    summary["demand_unpriced"] = unpriced
    summary["demand_gaps"] = len(priced)
    # Variants of a subject fold into one page across both sources.
    return GapScan(gaps=fold_variants(priced + from_competitors), summary=summary)
