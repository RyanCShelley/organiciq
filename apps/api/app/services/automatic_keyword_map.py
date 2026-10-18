"""Build supported ownership; leave ambiguity for review and preserve overrides."""
import re
from datetime import date, timedelta
from urllib.parse import urlsplit

from app.core.urls import normalize_url
from app.models.crawl import FactCrawlPageSnapshot
from app.models.decision import KeywordTarget
from app.models.seranking import FactSerKeyword
from app.models.watch_target import WatchTarget
from app.services.crawl_source import active_crawl_source
from app.services.keyword_matcher import DEFAULT_MARGIN, suggestions_for
from app.services.query_pages import pages_for_queries
from app.services.watchlist import item_key


def build(db, client, *, today=None):
    today = today or date.today()
    targets = {row.keyword: row for row in db.query(KeywordTarget).filter_by(client_id=client.id)}
    overrides = {row.item_key for row in db.query(WatchTarget).filter_by(client_id=client.id, kind="keyword")}
    tracked = db.query(FactSerKeyword).filter_by(client_id=client.id).all()
    terms = {(row.keyword or "").strip().lower() for row in tracked} - {""}
    observations = pages_for_queries(db, client.id, period=(today - timedelta(days=29), today), only=terms)
    subjects = suggestions_for(db, client.id)
    crawled = db.query(FactCrawlPageSnapshot).filter_by(client_id=client.id, source=active_crawl_source()).all()
    newest = max((row.snapshot_date for row in crawled), default=None)
    pages = {normalize_url(row.normalized_url): row for row in crawled if row.snapshot_date == newest and row.normalized_url}
    host = urlsplit(client.domain if "://" in client.domain else f"https://{client.domain}").hostname
    host = (host or "").lower().removeprefix("www.")
    def usable(value):
        if not value:
            return None
        url = normalize_url(value)
        page = pages.get(url)
        if page and page.canonical_url and normalize_url(page.canonical_url) != url:
            url = normalize_url(page.canonical_url)
            page = pages.get(url)
        if not page or not page.indexable or (page.canonical_url and normalize_url(page.canonical_url) != url) or (urlsplit(url).hostname or "").removeprefix("www.") != host:
            return None
        if client.path_prefix and not (urlsplit(url).path.rstrip("/") == client.path_prefix.rstrip("/") or urlsplit(url).path.startswith(client.path_prefix.rstrip("/") + "/")):
            return None
        return url
    summary = {"mapped": 0, "preserved": 0, "gaps": 0, "conflicts": 0}
    seen = set()
    for tracked_row in tracked:
        term = (tracked_row.keyword or "").strip().lower()
        if not term or term in seen:
            continue
        seen.add(term)
        old = targets.get(term)
        if (old and old.source == "confirmed") or item_key("keyword", term) in overrides:
            summary["preserved"] += 1
            continue
        subject = subjects.get(term)
        subject_url = usable(subject.page_url) if subject and subject.computed_on >= today - timedelta(days=45) and float(subject.margin) >= float(client.keyword_match_margin if client.keyword_match_margin is not None else DEFAULT_MARGIN) else None
        observed = observations.get(term)
        gsc_url = usable(observed.page_url) if observed and observed.impressions >= 30 else None
        rank_url = usable(tracked_row.ranking_url) if tracked_row.current_position and 0 < float(tracked_row.current_position) <= 100 else None
        candidates = {url for url in (gsc_url, rank_url) if url}
        # Ranking elsewhere can signal the wrong page, so a conflict with the
        # subject match is reviewed, never resolved by blindly trusting GSC.
        conflict = bool(subject_url and candidates - {subject_url}) or len(candidates) > 1
        chosen = None if conflict else subject_url
        basis = "subject match" if chosen else ""
        if not chosen and not conflict:
            url = gsc_url or rank_url
            if url:
                text = f"{pages[url].title or ''} {' '.join(str(x.get('text') or x.get('heading') or '') for x in (pages[url].sections or []) if isinstance(x, dict))}"
                tokens = set(re.findall(r"[a-z0-9]+", term))
                topical = tokens and tokens <= set(re.findall(r"[a-z0-9]+", text.lower()))
                if topical:
                    chosen, basis = url, "observed ranking and page topic"
        if not chosen:
            summary["conflicts" if conflict else "gaps"] += 1
            if old and old.source == "auto":
                old.source = "suggested"  # retain prior evidence without using stale ownership
            continue
        if old is None:
            old = KeywordTarget(client_id=client.id, keyword=term, priority=False)
            db.add(old)
        old.target_url, old.source = chosen, "auto"
        old.group_name = old.group_name or tracked_row.group_name
        old.confidence = subject.score if subject_url == chosen else None
        old.note = f"Automatically mapped from {basis} on {today.isoformat()}. Override to choose a different owner."
        summary["mapped"] += 1
    db.flush()
    return summary
