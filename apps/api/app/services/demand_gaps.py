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

import re
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
    is_noise_query,
    is_topically_relevant,
)
from app.models.client import Client
from app.models.config import Topic, TopicStatus
from app.models.crawl import FactCrawlPageSnapshot
from app.models.decision import KeywordTarget
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerCompetitorKeyword, FactSerKeyword, FactSerKeywordMetric
from app.models.watch_target import WatchTarget
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services.content_gap_signals import MIN_CRAWLED_PAGES, NEAREST_PAGES, GapScan
from app.services.page_signals import (
    effective_brand_terms,
    is_navigational,
    is_rival_navigational,
    is_substantive_page as _is_substantive_page,
    rival_brand_term_groups,
    rival_brand_terms_for_domains,
    rival_core_vocab_from_pages,
)

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


def _norm_term(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _punct_norm_term(value: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).split())


def _excluded_terms(db: Session, client: Client) -> set[str]:
    terms: set[str] = set()
    for (text,) in db.query(WatchTarget.text).filter(
        WatchTarget.client_id == client.id,
        WatchTarget.kind == "keyword",
        WatchTarget.state == "excluded",
    ):
        norm = _norm_term(text)
        if norm:
            terms.add(norm)
        punct_norm = _punct_norm_term(text)
        if punct_norm:
            terms.add(punct_norm)
    return terms


def _is_excluded(term: str, excluded: set[str]) -> bool:
    return _norm_term(term) in excluded or _punct_norm_term(term) in excluded


def _vocab_sets(
    db: Session,
    client: Client,
    pages: dict,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return (core_vocab, platform_allowed_words) excluding utility/boilerplate chrome."""
    substantive_parts: list[str] = []
    extra_parts: list[str] = []
    for url, row in pages.items():
        if not _is_substantive_page(url, row):
            continue
        headings = [
            str(s.get("heading") or "") for s in (row.sections or []) if isinstance(s, dict)
        ]
        substantive_parts.extend([row.title or "", urlsplit(url).path, *headings])
        if row.description:
            extra_parts.append(str(row.description))
        for q in row.faq_questions or ():
            if q:
                extra_parts.append(str(q))

    strategy_parts: list[str] = []
    for (kw,) in db.query(WatchlistKeyword.keyword).filter(
        WatchlistKeyword.client_id == client.id
    ):
        if kw:
            strategy_parts.append(str(kw))
    for (name,) in db.query(WatchlistBucket.name).filter(
        WatchlistBucket.client_id == client.id
    ):
        if name:
            strategy_parts.append(str(name))
    for kw, group_name in db.query(
        FactSerKeyword.keyword, FactSerKeyword.group_name
    ).filter(
        FactSerKeyword.client_id == client.id,
        FactSerKeyword.is_tracked.is_(True),
    ):
        if kw:
            strategy_parts.append(str(kw))
        if group_name:
            strategy_parts.append(str(group_name))
    for (text,) in db.query(WatchTarget.text).filter(
        WatchTarget.client_id == client.id,
        WatchTarget.kind == "keyword",
        WatchTarget.state != "excluded",
    ):
        if text:
            strategy_parts.append(str(text))
    for (topic_name,) in db.query(Topic.topic_name).filter(
        Topic.client_id == client.id,
        Topic.status == TopicStatus.ACTIVE,
    ):
        if topic_name:
            strategy_parts.append(str(topic_name))

    market_parts: list[str] = [str(client.primary_market)] if client.primary_market else []
    platform_allowed_words = frozenset().union(
        *(content_words(part) for part in (substantive_parts + strategy_parts) if part)
    )
    core_vocab = platform_allowed_words | frozenset().union(
        *(content_words(part) for part in (extra_parts + market_parts) if part)
    )
    return core_vocab, platform_allowed_words


def _core_vocab(
    db: Session,
    client: Client,
    pages: dict,
    everywhere: frozenset[str],
) -> frozenset[str]:
    """Broader domain vocabulary from substantive crawl metadata, watchlist, tracked terms, topics, and market."""
    core_vocab, _ = _vocab_sets(db, client, pages)
    return core_vocab if pages else everywhere


def _rival_core_vocab(client: Client, pages: dict) -> frozenset[str]:
    """Substantive crawl words plus primary market, excluding strategy/tracked terms."""
    return rival_core_vocab_from_pages(client, pages)


def _raw_demand_candidates(
    db: Session, client: Client, *, today: date | None = None
) -> tuple[list[DemandGap], dict[str, int], str | None]:
    """Pre-fold unpriced demand gaps so callers can fold or look up exact per-query metadata."""
    today = today or date.today()
    start = today - timedelta(days=LOOKBACK_DAYS)

    site = _load_site(db, client)
    if isinstance(site, str):
        return [], {}, site
    pages, page_words, everywhere = site

    bind = db.get_bind()
    is_postgres = bind is not None and bind.dialect.name == "postgresql"
    norm_gsc_query = (
        func.trim(func.regexp_replace(func.lower(FactGscQueryPage.query), r"\s+", " ", "g"))
        if is_postgres
        else func.lower(func.trim(FactGscQueryPage.query))
    )
    rows = (
        db.query(
            norm_gsc_query,
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
        .group_by(norm_gsc_query, FactGscQueryPage.normalized_url)
        .all()
    )
    by_query_url: dict[str, dict[str, list[float]]] = defaultdict(dict)
    for query, url, impressions, clicks, weighted_position in rows:
        norm_query = _norm_term(query)
        if norm_query and url:
            totals = by_query_url[norm_query].get(url)
            if totals is None:
                by_query_url[norm_query][url] = [
                    float(impressions or 0),
                    float(clicks or 0),
                    float(weighted_position or 0),
                ]
            else:
                totals[0] += float(impressions or 0)
                totals[1] += float(clicks or 0)
                totals[2] += float(weighted_position or 0)
    by_query: dict[str, list[tuple[str, float, float, float]]] = {
        norm_query: [(url, vals[0], vals[1], vals[2]) for url, vals in url_map.items()]
        for norm_query, url_map in by_query_url.items()
    }

    tracked = {
        _norm_term(row[0])
        for row in db.query(FactSerKeyword.keyword).filter(FactSerKeyword.client_id == client.id)
        if _norm_term(row[0])
    }
    targeted = {
        _norm_term(row[0])
        for row in db.query(KeywordTarget.keyword).filter(KeywordTarget.client_id == client.id)
        if _norm_term(row[0])
    }
    excluded = _excluded_terms(db, client)
    brand = effective_brand_terms(db, client)
    exact_rival, emd_rival = rival_brand_term_groups(db, client)
    core_vocab, platform_allowed_words = _vocab_sets(db, client, pages)
    rival_core_vocab = _rival_core_vocab(client, pages)

    summary = {
        "demand_queries": len(by_query),
        "demand_tracked": 0,
        "demand_excluded": 0,
        "demand_brand": 0,
        "demand_noise": 0,
        "demand_off_topic": 0,
        "demand_small": 0,
        "demand_earning": 0,
        "demand_covered": 0,
    }
    gaps: list[DemandGap] = []
    for query, shown in by_query.items():
        if query in tracked or query in targeted:
            summary["demand_tracked"] += 1
            continue
        if _is_excluded(query, excluded):
            summary["demand_excluded"] += 1
            continue
        if is_navigational(query, brand) or is_rival_navigational(
            query, exact_terms=exact_rival, emd_terms=emd_rival, core_vocab=rival_core_vocab
        ):
            summary["demand_brand"] += 1
            continue
        if is_noise_query(query, strict_platforms=True, allowed_words=platform_allowed_words):
            summary["demand_noise"] += 1
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
            summary["demand_noise"] += 1
            continue
        if not is_topically_relevant(words, core_vocab=core_vocab):
            summary["demand_off_topic"] += 1
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

    return gaps, summary, None


def demand_candidates(
    db: Session, client: Client, *, today: date | None = None
) -> tuple[list[DemandGap], dict[str, int], str | None]:
    """Unpriced demand gaps, largest first, with the counts behind them.

    The third value is set when the scan cannot say anything: a crawl that
    saw too few pages cannot show that a query has no page.
    """
    raw_gaps, summary, blocked = _raw_demand_candidates(db, client, today=today)
    if blocked:
        return [], summary, blocked
    return fold_variants(raw_gaps), summary, None


def _competitor_rows(db: Session, client: Client) -> dict[str, dict]:
    """What the competitors rank in the top ten for, one entry per query.

    Volume and difficulty are SE Ranking's own, from the same request that
    named the term; the largest volume reported wins when competitors differ.
    """
    found: dict[str, dict] = {}
    for row in db.query(FactSerCompetitorKeyword).filter(
        FactSerCompetitorKeyword.client_id == client.id
    ):
        term = _norm_term(row.keyword)
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
    return rival_brand_terms_for_domains(domains)


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
        "competitor_excluded": 0,
        "competitor_brand": 0,
        "competitor_noise": 0,
        "competitor_off_topic": 0,
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
        _norm_term(row[0])
        for row in db.query(FactSerKeyword.keyword).filter(FactSerKeyword.client_id == client.id)
        if _norm_term(row[0])
    } | {
        _norm_term(row[0])
        for row in db.query(KeywordTarget.keyword).filter(KeywordTarget.client_id == client.id)
        if _norm_term(row[0])
    }
    excluded = _excluded_terms(db, client)
    brand = effective_brand_terms(db, client)
    exact_rival, emd_rival = rival_brand_term_groups(
        db,
        client,
        extra_domains={domain for entry in ranked.values() for domain in entry["rivals"]},
    )
    core_vocab, platform_allowed_words = _vocab_sets(db, client, pages)
    rival_core_vocab = _rival_core_vocab(client, pages)

    start = today - timedelta(days=LOOKBACK_DAYS)
    shown_by_url: dict[str, dict[str, list[float]]] = defaultdict(dict)
    candidates = [t for t in ranked if t not in skip]
    bind = db.get_bind()
    is_postgres = bind is not None and bind.dialect.name == "postgresql"
    if is_postgres:
        norm_gsc_query = func.trim(
            func.regexp_replace(func.lower(FactGscQueryPage.query), r"\s+", " ", "g")
        )
        for offset in range(0, len(candidates), 500):
            chunk = candidates[offset : offset + 500]
            for query, url, impressions, clicks, weighted in (
                db.query(
                    norm_gsc_query,
                    FactGscQueryPage.normalized_url,
                    func.sum(FactGscQueryPage.impressions),
                    func.sum(FactGscQueryPage.clicks),
                    func.sum(FactGscQueryPage.impressions * FactGscQueryPage.average_position),
                )
                .filter(
                    FactGscQueryPage.client_id == client.id,
                    FactGscQueryPage.date >= start,
                    FactGscQueryPage.date <= today,
                    norm_gsc_query.in_(chunk),
                )
                .group_by(norm_gsc_query, FactGscQueryPage.normalized_url)
            ):
                norm_query = _norm_term(query)
                if norm_query and url:
                    totals = shown_by_url[norm_query].get(url)
                    if totals is None:
                        shown_by_url[norm_query][url] = [
                            float(impressions or 0),
                            float(clicks or 0),
                            float(weighted or 0),
                        ]
                    else:
                        totals[0] += float(impressions or 0)
                        totals[1] += float(clicks or 0)
                        totals[2] += float(weighted or 0)
    else:
        candidate_set = set(candidates)
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
            )
            .group_by(
                func.lower(func.trim(FactGscQueryPage.query)), FactGscQueryPage.normalized_url
            )
        ):
            norm_query = _norm_term(query)
            if norm_query and url and norm_query in candidate_set:
                totals = shown_by_url[norm_query].get(url)
                if totals is None:
                    shown_by_url[norm_query][url] = [
                        float(impressions or 0),
                        float(clicks or 0),
                        float(weighted or 0),
                    ]
                else:
                    totals[0] += float(impressions or 0)
                    totals[1] += float(clicks or 0)
                    totals[2] += float(weighted or 0)
    shown: dict[str, list[tuple[str, float, float, float]]] = {
        norm_query: [(url, vals[0], vals[1], vals[2]) for url, vals in url_map.items()]
        for norm_query, url_map in shown_by_url.items()
    }

    gaps: list[DemandGap] = []
    for term in candidates:
        entry = ranked[term]
        if term in tracked:
            summary["competitor_tracked"] += 1
            continue
        if _is_excluded(term, excluded):
            summary["competitor_excluded"] += 1
            continue
        if is_navigational(term, brand) or is_rival_navigational(
            term, exact_terms=exact_rival, emd_terms=emd_rival, core_vocab=rival_core_vocab
        ):
            summary["competitor_brand"] += 1
            continue
        if is_noise_query(term, strict_platforms=True, allowed_words=platform_allowed_words):
            summary["competitor_noise"] += 1
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
            summary["competitor_noise"] += 1
            continue
        if not is_topically_relevant(words, core_vocab=core_vocab):
            summary["competitor_off_topic"] += 1
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
        _norm_term(row[0])
        for row in db.query(FactSerKeywordMetric.keyword).filter(
            FactSerKeywordMetric.client_id == client.id
        )
        if _norm_term(row[0])
    }
    priced |= {
        term
        for term, entry in _competitor_rows(db, client).items()
        if entry["volume"] is not None and entry["difficulty"] is not None
    }
    return [g.term for g in gaps if g.term not in priced][:PRICING_LIMIT]


def _qualifying_price(
    term: str,
    prices: dict[str, FactSerKeywordMetric],
    rivals: dict[str, dict],
) -> tuple[float, float, tuple[str, ...], dict | None] | None:
    row = prices.get(term)
    rival = rivals.get(term)
    if (
        row is not None
        and row.data_found
        and row.difficulty is not None
        and row.volume
        and float(row.volume) >= MIN_VOLUME
    ):
        return float(row.volume), float(row.difficulty), tuple(row.intents or ()), rival
    if (
        rival is not None
        and rival["volume"]
        and float(rival["volume"]) >= MIN_VOLUME
        and rival["difficulty"] is not None
    ):
        return float(rival["volume"]), float(rival["difficulty"]), (), rival
    return None


def scan_demand_gaps(db: Session, client: Client, *, today: date | None = None) -> GapScan:
    """Demand gaps with prices: Search Console's, and the competitors' beyond them."""
    raw_gaps, summary, blocked = _raw_demand_candidates(db, client, today=today)
    if blocked:
        return GapScan(gaps=[], blocked=blocked)
    raw_by_term = {g.term: g for g in raw_gaps}
    gaps = fold_variants(raw_gaps)

    prices = {
        _norm_term(row.keyword): row
        for row in db.query(FactSerKeywordMetric).filter(
            FactSerKeywordMetric.client_id == client.id
        )
        if _norm_term(row.keyword)
    }
    rivals = _competitor_rows(db, client)

    priced: list[DemandGap] = []
    unpriced_gaps: list[DemandGap] = []
    unpriced = 0
    for gap in gaps:
        q_price = _qualifying_price(gap.term, prices, rivals)
        if q_price is not None:
            volume, difficulty, intents, rival = q_price
            found = replace(
                gap,
                volume=volume,
                difficulty=difficulty,
                intents=intents,
            )
        else:
            variant_matches: list[
                tuple[float, float, str, tuple[float, float, tuple[str, ...], dict | None]]
            ] = []
            for alt_term, alt_imp in gap.also_covers:
                alt_price = _qualifying_price(_norm_term(alt_term), prices, rivals)
                if alt_price is not None:
                    vol, diff, _, _ = alt_price
                    opp = max(0.0, vol * (1.0 - min(diff, 100.0) / 100.0))
                    variant_matches.append((opp, float(alt_imp), alt_term, alt_price))
            if variant_matches:
                _, best_imp, best_term, (volume, difficulty, intents, rival) = min(
                    variant_matches,
                    key=lambda item: (-item[0], -item[1], item[2]),
                )
                remaining_covers = sorted(
                    [(gap.term, gap.impressions), *(pair for pair in gap.also_covers if pair[0] != best_term)],
                    key=lambda pair: (-pair[1], pair[0]),
                )
                best_raw = raw_by_term.get(best_term, gap)
                found = replace(
                    best_raw,
                    impressions=best_imp,
                    volume=volume,
                    difficulty=difficulty,
                    intents=intents,
                    also_covers=tuple(remaining_covers),
                )
            else:
                unpriced += 1
                if prices.get(gap.term) is None and rivals.get(gap.term) is None:
                    unpriced_gaps.append(gap)
                continue
        if rival is not None:
            found = replace(
                found,
                competitors=tuple(
                    sorted(rival["rivals"].items(), key=lambda pair: (pair[1], pair[0]))
                ),
            )
        priced.append(found)

    skip = {g.term for g in gaps} | {alt for g in gaps for alt, _ in g.also_covers}
    from_competitors, competitor_summary = competitor_candidates(
        db, client, skip=skip, today=today
    )
    summary.update(competitor_summary)
    summary["demand_unpriced"] = unpriced
    summary["demand_gaps"] = len(priced)
    # Variants of a subject fold into one page across both sources.
    return GapScan(
        gaps=fold_variants(priced + from_competitors),
        summary=summary,
        unpriced=tuple(unpriced_gaps),
    )
