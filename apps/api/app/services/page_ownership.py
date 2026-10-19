"""Compare intended page ownership, independently of saved human overrides.

Scores are evidence weights, not probabilities. A search appearance is a
candidate signal, never a substitute for a readable, intent-compatible page.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
import re
from urllib.parse import urlsplit

from app.core.urls import normalize_url, url_in_scope

NEUTRAL = set('a an the and or of for to with your our us is are be in on at by from that this as near me company companies agency agencies service services provider providers solution solutions swimming'.split())
INFO = re.compile(r'^(how|what|why|when|where|can|does|do|is|are|best|top|benefits|types|guide)\b|\b(vs|versus)\b', re.I)
COMMERCIAL = re.compile(r'\b(services?|compan(?:y|ies)|agenc(?:y|ies)|providers?|consulting|support|repair|management|training|solutions?)\b', re.I)
ARTICLE_PATH = re.compile(r'/(blog|articles?|news|guides?|glossary|resources)/|/(how|what|why|benefits|types|top|best)-', re.I)
LOCATION_PATH = re.compile(r'/(?:locations?|service-areas?|areas-served)/([^/]+)', re.I)
SCOPE = re.compile(r'\b(?i:in|throughout|serving|across)\s+([A-Z][^.!?;|:]{1,100})')


def tokens(value):
    value = re.sub(r'cyber\s+security', 'cybersecurity', (value or '').lower())
    value = re.sub(r'search engine optimi[sz]ation', 'seo', value)
    out = set()
    for word in re.findall(r'[a-z0-9]+', value):
        if word in NEUTRAL:
            continue
        if len(word) > 4 and word.endswith('ies'):
            word = word[:-3] + 'y'
        elif len(word) > 4 and word.endswith('s') and not word.endswith(('ss', 'us')):
            word = word[:-1]
        out.add(word)
    return out


def primary_options(page):
    headings = [str(s.get('heading') or s.get('text') or '') for s in (page.sections or [])
                if isinstance(s, dict) and s.get('level') == 1]
    return [v for v in [*headings, *re.split(r'\|| - ', page.title or '')] if v.strip()]


def primary_text(page):
    h1 = [str(s.get('heading') or s.get('text') or '') for s in (page.sections or [])
          if isinstance(s, dict) and s.get('level') == 1]
    return ' '.join(h1) or (page.title or '').split('|')[0].split(' - ')[0]


def location_tokens(page):
    """Infer scope from the site's own URL and primary headings, not a city list.

    A homepage may describe its region and still own the broad business topic.
    Body copy/footer mentions alone cannot turn a page into a location page.
    """
    path = urlsplit(page.normalized_url).path
    if path == '/':
        return set()
    explicit = LOCATION_PATH.search(path)
    scope = tokens(explicit.group(1)) if explicit else set()
    headings = [str(s.get('heading') or '') for s in (page.sections or [])[:4]
                if isinstance(s, dict) and s.get('level') in (1, 2)]
    for heading in [page.title or '', *headings]:
        for match in SCOPE.finditer(heading):
            found = tokens(match.group(1))
            # Require agreement with the page URL. Generic prose such as
            # "Invest in Cloud Solutions" is not independently a location.
            overlap = found & tokens(path)
            if overlap:
                scope |= overlap
            elif re.search(r'\b(?:County|Counties|City|Bay|Region)\b', match.group(1)):
                scope |= found
    return scope - {'location', 'area', 'county', 'city', 'region'}


def article(page):
    return bool(ARTICLE_PATH.search(urlsplit(page.normalized_url).path)
                or INFO.search(primary_text(page)))


@dataclass
class Ownership:
    url: str | None
    status: str
    reason: str
    candidates: list[dict] = field(default_factory=list)


class PageIndex:
    def __init__(self, pages, domain, path_prefix=None, today=None):
        self.host = (urlsplit(domain if '://' in domain else 'https://' + domain).hostname or '').removeprefix('www.')
        self.path_prefix = path_prefix
        today = today or date.today()
        newest = max((p.snapshot_date for p in pages), default=None)
        self.pages = {normalize_url(p.normalized_url): p for p in pages
                      if p.normalized_url and p.snapshot_date == newest
                      and today - timedelta(days=45) <= p.snapshot_date <= today}
        self.eligible = {}
        for url in sorted(self.pages):
            resolved = self.resolve(url)
            if resolved:
                self.eligible[resolved] = self.pages[resolved]

    def resolve(self, value):
        if not value:
            return None
        if value.startswith('/'):
            value = 'https://' + self.host + value
        url = normalize_url(value)
        seen = set()
        while url not in seen:
            seen.add(url)
            if (urlsplit(url).hostname or '').removeprefix('www.') != self.host:
                return None
            page = self.pages.get(url)
            if not page:
                return None
            dest = page.redirect_url or page.canonical_url
            if dest:
                dest = normalize_url('https://' + self.host + dest if dest.startswith('/') else dest)
                if dest != url:
                    url = dest
                    continue
            if ((urlsplit(url).hostname or '').removeprefix('www.') != self.host
                or not url_in_scope(url, self.path_prefix) or not page.indexable
                or page.soft_404 or page.blocked_by_robots
                or (page.status_code is not None and page.status_code != 200)
                or not primary_text(page).strip()):
                return None
            return url
        return None


def choose(term, index, *, subject=None, gsc=(), rankings=(), current=(), today=None, margin=.10):
    today = today or date.today()
    core = tokens(term)
    if not core:
        return Ownership(None, 'gap', 'No specific topic to compare.')
    informational = bool(INFO.search(term))
    commercial = not informational and bool(COMMERCIAL.search(term))
    subject_url = None
    if (subject and today - timedelta(days=45) <= subject.computed_on <= today
        and float(subject.margin) >= margin):
        subject_url = index.resolve(subject.page_url)
    gsc_by_url = {}
    for row in gsc:
        url = index.resolve(row['url'])
        if url and row['days'] >= 3 and float(row['impressions']) >= 30 and today - timedelta(days=14) <= row['last_date'] <= today:
            gsc_by_url[url] = gsc_by_url.get(url, 0) + float(row['impressions'])
    gsc_total = sum(gsc_by_url.values())
    # One vote per date and market. A duplicated tracker row cannot manufacture
    # persistence, and conflicting markets remain competing evidence.
    votes = {}
    for row in rankings:
        if row['position'] and 0 < float(row['position']) <= 100 and today - timedelta(days=29) <= row['date'] <= today:
            url = index.resolve(row['url'])
            if url:
                votes[(row['date'], row['site_engine_id'], url)] = url
    rank_counts = {}
    for url in set(votes.values()):
        dates = {key[0] for key, value in votes.items() if value == url}
        if (len(dates) >= 3 and (max(dates) - min(dates)).days >= 7
            and max(dates) >= today - timedelta(days=14)):
            rank_counts[url] = sum(value == url for value in votes.values())
    rank_total = sum(rank_counts.values())
    current_urls = {index.resolve(r.ranking_url) for r in current
                    if r.checked_at and today - timedelta(days=7) <= r.checked_at <= today
                    and r.current_position and 0 < float(r.current_position) <= 100} - {None}
    candidates = []
    for url, page in index.eligible.items():
        options = [(len(core & tokens(text)) / len(core), len(core & tokens(text)) / max(len(tokens(text)), 1))
                   for text in primary_options(page)]
        coverage, precision = max(options, key=lambda values: .40 * values[0] + .45 * values[1])
        if coverage < .80:
            continue
        scope = location_tokens(page)
        reasons = []
        path = urlsplit(url).path
        sector = re.search(r'/industries/([^/]+)', path)
        if sector and not core & tokens(sector.group(1)):
            reasons.append('Industry-specific page does not match the query audience.')
        if commercial and path.rstrip('/') in ('/blog', '/glossary', '/resources', '/locations', '/industries'):
            reasons.append('Section index does not establish individual service ownership.')
        if commercial and re.match(r'^/(company|about(?:-us)?|team|contact|careers)(/|$)', path):
            reasons.append('Company information page does not establish service ownership.')
        # A specialist service (e.g. local SEO) does not automatically own
        # its broader parent topic (SEO). The site's own service slug names
        # the specialization; no client-specific dictionary is needed.
        service = re.search(r'/(?:capabilities|services)/([^/]+)$', path)
        if service and tokens(service.group(1)) > core:
            reasons.append('Specialist service page is narrower than the query topic.')
        if scope and not core & scope:
            reasons.append('Location-specific page does not match the query location.')
        is_article = article(page)
        if commercial and is_article:
            reasons.append('Informational page does not match service intent.')
        if informational and not is_article:
            reasons.append('Service page does not match informational intent.')
        signals = ['primary page topic']
        score = .40 * coverage + .45 * precision
        slug = tokens(urlsplit(url).path.rstrip('/').split('/')[-1])
        if slug == core:
            score += .20
            signals.append('matching page URL topic')
        if term.lower() in ' '.join(primary_options(page)).lower():
            score += .12
        if url == subject_url:
            score += .15; signals.append('qualified subject match')
        if gsc_total and url in gsc_by_url:
            score += .20 * gsc_by_url[url] / gsc_total; signals.append('multi-day Search Console evidence')
        if rank_total and url in rank_counts:
            score += .20 * rank_counts[url] / rank_total; signals.append('persistent tracked landing page')
        if url in current_urls:
            score += .05; signals.append('recent tracked landing page')
        # Editorial support is only a tiebreaker, never an ownership trigger.
        score += min(page.inbound_editorial_links or 0, 20) / 1000
        candidates.append({'url': url, 'score': round(score, 4), 'eligible': not reasons,
                           'signals': signals, 'limits': reasons, 'topic_precision': round(precision, 4)})
    candidates.sort(key=lambda r: (-r['score'], r['url']))
    eligible = [r for r in candidates if r['eligible']]
    audit = eligible[:3] + [r for r in candidates if not r['eligible']][:3]
    if not eligible:
        return Ownership(None, 'gap', 'No readable page matches the topic and intent.', audit)
    best = eligible[0]
    recent_votes = {key: value for key, value in votes.items() if key[0] >= today - timedelta(days=6)}
    recent_dates = {key[0] for key in recent_votes}
    stable_urls = set(recent_votes.values()) if len(recent_dates) >= 3 else set()
    eligible_urls = {r['url'] for r in eligible}
    if len(stable_urls) == 1 and stable_urls <= eligible_urls and best['url'] not in stable_urls:
        return Ownership(None, 'conflict', 'Recent persistent landing page conflicts with the proposed owner; ownership withheld.', audit)
    runner = eligible[1]['score'] if len(eligible) > 1 else 0
    # A precise, unique primary subject can establish ownership without a
    # search impression. Otherwise require independent supporting evidence.
    grounded = len(best['signals']) > 1 or best['topic_precision'] >= .90
    if best['score'] < .70 or best['score'] - runner < .12 or not grounded:
        return Ownership(None, 'conflict', 'Competing pages or insufficient independent evidence; ownership withheld.', audit)
    reason = '; '.join(best['signals']) + f"; evidence margin {best['score'] - runner:.2f}"
    return Ownership(best['url'], 'mapped', reason, audit)
