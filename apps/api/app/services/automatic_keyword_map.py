"""Build supported ownership; preserve explicit decisions and explain uncertainty."""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func
from app.models.crawl import FactCrawlPageSnapshot
from app.models.decision import KeywordTarget
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerKeyword, FactSerRanking
from app.models.watch_target import WatchTarget
from app.services.crawl_source import active_crawl_source
from app.services.keyword_matcher import DEFAULT_MARGIN, suggestions_for
from app.services.page_ownership import PageIndex, choose
from app.services.watchlist import item_key


def evaluate(db, client, *, today=None):
    """Read-only decisions, including confirmed terms for counterfactual QA."""
    today = today or date.today()
    tracked = db.query(FactSerKeyword).filter_by(client_id=client.id, is_tracked=True).all()
    by_term = defaultdict(list)
    cohort = {}
    for row in tracked:
        term = (row.keyword or '').strip().lower()
        if term:
            by_term[term].append(row)
            cohort[(row.site_engine_id, row.keyword_id)] = term
    terms = set(by_term)
    pages = db.query(FactCrawlPageSnapshot).filter_by(client_id=client.id, source=active_crawl_source()).all()
    index = PageIndex(pages, client.domain, client.path_prefix, today=today)
    gsc = defaultdict(list)
    if terms:
        rows = db.query(func.lower(func.trim(FactGscQueryPage.query)), FactGscQueryPage.normalized_url,
            func.sum(FactGscQueryPage.impressions), func.count(func.distinct(FactGscQueryPage.date)),
            func.max(FactGscQueryPage.date)).filter(FactGscQueryPage.client_id == client.id,
            FactGscQueryPage.date >= today - timedelta(days=89), FactGscQueryPage.date <= today,
            func.lower(func.trim(FactGscQueryPage.query)).in_(terms)).group_by(
            func.lower(func.trim(FactGscQueryPage.query)), FactGscQueryPage.normalized_url).all()
        for term, url, impressions, days, last_date in rows:
            gsc[term].append({'url': url, 'impressions': float(impressions or 0), 'days': days, 'last_date': last_date})
    rankings = defaultdict(list)
    for row in db.query(FactSerRanking).filter(FactSerRanking.client_id == client.id,
        FactSerRanking.date >= today - timedelta(days=29), FactSerRanking.date <= today):
        term = cohort.get((row.site_engine_id, row.keyword_id))
        if term and (row.keyword or '').strip().lower() == term:
            rankings[term].append({'url': row.ranking_url, 'position': row.position,
                                  'date': row.date, 'site_engine_id': row.site_engine_id})
    subjects = suggestions_for(db, client.id)
    margin = float(client.keyword_match_margin if client.keyword_match_margin is not None else DEFAULT_MARGIN)
    return {term: choose(term, index, subject=subjects.get(term), gsc=gsc[term],
                        rankings=rankings[term], current=by_term[term], today=today, margin=margin)
            for term in sorted(terms)}


def build(db, client, *, today=None):
    today = today or date.today()
    targets = {row.keyword: row for row in db.query(KeywordTarget).filter_by(client_id=client.id)}
    overrides = {row.item_key for row in db.query(WatchTarget).filter_by(client_id=client.id, kind='keyword')}
    decisions = evaluate(db, client, today=today)
    groups = {row.keyword.strip().lower(): row.group_name for row in db.query(FactSerKeyword).filter_by(client_id=client.id, is_tracked=True)}
    summary = {'mapped': 0, 'preserved': 0, 'gaps': 0, 'conflicts': 0}
    for term, decision in decisions.items():
        old = targets.get(term)
        if (old and old.source == 'confirmed') or item_key('keyword', term) in overrides:
            summary['preserved'] += 1
            continue
        if not decision.url:
            summary['conflicts' if decision.status == 'conflict' else 'gaps'] += 1
            if old and old.source == 'auto':
                old.source = 'suggested'
                old.confidence = None
                old.note = f'Ownership withheld on {today.isoformat()}: {decision.reason}'
            continue
        if old is None:
            old = KeywordTarget(client_id=client.id, keyword=term, priority=False)
            db.add(old)
        old.target_url, old.source = decision.url, 'auto'
        old.group_name = old.group_name or groups.get(term)
        old.confidence = None  # evidence weights are not calibrated probabilities
        old.note = f'Automatically mapped on {today.isoformat()}: {decision.reason}. Explicit decisions are preserved.'
        summary['mapped'] += 1
    db.flush()
    return summary
