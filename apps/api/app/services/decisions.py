from __future__ import annotations





def upsert_keyword_page_map(db, client_id, entries):
    """Record or update which page owns each term.

    Keywords are stored lowercase: a watchlist entry and a Search Console
    query differ in case far more often than in substance, and the engine
    looks the mapping up by the lowercased term.
    """
    from app.models.decision import KeywordTarget

    wanted = [k for k in ((e.keyword or "").strip().lower() for e in entries) if k]
    # Every row this save might touch, in one query rather than one per
    # entry — a bulk save of a hundred keywords was a hundred round trips.
    existing = {
        row.keyword: row
        for row in db.query(KeywordTarget).filter(
            KeywordTarget.client_id == client_id,
            KeywordTarget.keyword.in_(wanted),
        )
    }
    for entry in entries:
        keyword = entry.keyword.strip().lower()
        if not keyword:
            continue
        row = existing.get(keyword)
        if row is None:
            row = KeywordTarget(client_id=client_id, keyword=keyword)
            db.add(row)
            # The batched lookup only saw what was in the table when it ran,
            # so a keyword repeated inside one payload has to be matched
            # against what this call has already added.
            existing[keyword] = row
        row.target_url = (entry.target_url or "").strip() or None
        row.term_role = entry.term_role
        row.group_name = (entry.group_name or "").strip() or None
        row.priority = bool(entry.priority)
        # Anything written through this path is somebody's decision. A
        # suggestion only becomes confirmed by passing through here.
        row.source = "confirmed"
        row.note = (entry.note or "").strip() or None
    db.commit()
    return (
        db.query(KeywordTarget)
        .filter(KeywordTarget.client_id == client_id)
        .order_by(KeywordTarget.keyword)
        .all()
    )


def _first_number(*values):
    """The first of these that is a real number, as a float."""
    for value in values:
        if value is None:
            continue
        number = float(value)
        if number:
            return number
    return None


def keyword_page_map_view(db, client_id, *, period=None):
    """Every tracked keyword with its mapping and the best guesses at one.

    The map is only useful if it is easy to fill in, and a blank list of
    keywords is not. Each row carries what the engine would have guessed —
    the page Search Console shows and where it ranks — so the decision is
    a confirmation rather than research.
    """
    from datetime import date, timedelta

    from app.models.crawl import FactCrawlPageSnapshot
    from app.models.decision import KeywordTarget
    from app.models.seranking import FactSerKeyword, FactSerKeywordMetric
    from app.services.crawl_source import active_crawl_source
    from app.services.query_pages import pages_for_queries, rank_position

    if period is None:
        today = date.today()
        period = (today - timedelta(days=29), today)

    mapped = {
        (row.keyword or "").strip().lower(): row
        for row in db.query(KeywordTarget)
        .filter(KeywordTarget.client_id == client_id)
        .all()
    }
    metrics = {
        (row.keyword or "").strip().lower(): row
        for row in db.query(FactSerKeywordMetric)
        .filter(FactSerKeywordMetric.client_id == client_id)
        .all()
    }
    tracked_rows = (
        db.query(FactSerKeyword).filter(FactSerKeyword.client_id == client_id).all()
    )
    # Only the tracked terms are ever looked up below, so only those are asked
    # for. This summarised every query the site has ever shown.
    tracked_keys = {(row.keyword or "").strip().lower() for row in tracked_rows} - {""}
    suggestions = pages_for_queries(db, client_id, period=period, only=tracked_keys)
    # Where Search Console shows a page, that wins: it is an observation.
    # The model fills the gap — a term that ranks nowhere has no observation
    # to offer, and after a relaunch the only page that ranks is the
    # homepage, so every observation points there.
    from app.services.keyword_matcher import suggestions_for

    by_subject = suggestions_for(db, client_id)

    # Where each page points its canonical. Search Console happily reports a
    # retired URL — smamarketing.com/services/local-seo still draws
    # impressions while telling Google to index /capabilities/local-seo —
    # and mapping a term to the page that asked to be ignored would bake the
    # mistake in permanently.
    canonical_of: dict[str, str] = {}
    crawled = (
        db.query(
            FactCrawlPageSnapshot.normalized_url,
            FactCrawlPageSnapshot.canonical_url,
            FactCrawlPageSnapshot.indexable,
        )
        .filter(
            FactCrawlPageSnapshot.client_id == client_id,
            FactCrawlPageSnapshot.source == active_crawl_source(),
        )
        .all()
    )
    for url, canonical, _indexable in crawled:
        if url and canonical and canonical != url:
            canonical_of[url] = canonical

    rows = []
    for tracked in tracked_rows:
        keyword = (tracked.keyword or "").strip()
        if not keyword:
            continue
        key = keyword.lower()
        row = mapped.get(key)
        metric = metrics.get(key)
        suggested = suggestions.get(key)
        proposed = by_subject.get(key)
        suggested_url = suggested.page_url if suggested else None
        suggested_from = "search_console" if suggested else None
        if suggested_url is None and proposed is not None:
            suggested_url = proposed.page_url
            suggested_from = "subject"
        redirected_from = None
        if suggested_url and suggested_url in canonical_of:
            redirected_from, suggested_url = suggested_url, canonical_of[suggested_url]
        rows.append(
            {
                "keyword": keyword,
                "target_url": row.target_url if row else None,
                "note": row.note if row else None,
                "mapped": row is not None,
                #: primary | secondary | None. Null is its own answer.
                "term_role": row.term_role if row else None,
                #: SE Ranking's own grouping, so the only new judgement is
                #: which groups are the priority ones.
                "group_name": (row.group_name if row else None) or tracked.group_name,
                "priority": bool(row.priority) if row else False,
                #: confirmed | suggested. The engine reads confirmed only.
                "source": row.source if row else None,
                #: The paid lookup prices every term, ranked or not, but it
                #: is only run monthly and the rank tracker already carries
                #: a volume for each term it tracks. Reading only the first
                #: left the column empty for every client the lookup had
                #: not been run for.
                "volume": _first_number(
                    metric.volume if metric else None, tracked.volume
                ),
                "difficulty": (
                    float(metric.difficulty) if metric and metric.difficulty else None
                ),
                "current_position": rank_position(tracked.current_position),
                "suggested_target_url": suggested_url,
                #: Which read it came from. They mean different things: one
                #: is where the site ranks, the other is what the page is
                #: about, and a person deciding should know which.
                "suggested_from": suggested_from,
                "suggested_margin": (
                    float(proposed.margin)
                    if proposed is not None and suggested_from == "subject"
                    else None
                ),
                "suggested_impressions": (
                    round(suggested.impressions) if suggested else None
                ),
                #: Set when the page Search Console reports canonicalises
                #: elsewhere, so the UI can say why it is offering a
                #: different URL than the data literally shows.
                "suggested_instead_of": redirected_from,
            }
        )
    rows.sort(key=lambda r: (r["mapped"], -(r["volume"] or 0), r["keyword"]))

    # Candidate pages for the picker: everything the crawl reached that can
    # actually hold a ranking.
    # Only pages that could actually hold the ranking: a page pointing its
    # canonical elsewhere has asked not to, so offering it in the picker
    # invites exactly the mistake above.
    pages = sorted(
        url
        for url, _canonical, indexable in crawled
        if url and indexable and url not in canonical_of
    )
    return {"keywords": rows, "pages": pages}
