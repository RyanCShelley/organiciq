"""Read the Traffic and Leads candidates out of the warehouse.

One page, every fact the T and L triggers test. Managed channels only, per
rule 4 — a session that arrived from a paid ad is not evidence about the
organic work, and counting it is how a page scored well on traffic nobody
here earned.

Where a fact is absent the field stays None and the trigger that needs it does
not fire. That is the point: an action nobody can justify is worse than a slot
that says why it is empty.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Iterable
from datetime import date, timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import UUID

from app.decisions.planning import page_identity
from app.services.page_ownership import location_tokens, tokens

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.ctr_curve import REFERENCE_SCENARIO, expected_ctr_percent
from app.decisions.page_targets import (
    CONTESTED_MIN_IMPRESSIONS,
    CONTESTED_MIN_RIVAL_SHARE,
    ContestedTerm,
    LinkDonor,
    PageCandidate,
    Rival,
)
from app.models.client import Client
from app.models.config import ClientConversionPage
from app.models.crawl import (
    CRAWL_SOURCE_FIRST_PARTY,
    FactCrawlInternalLink,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from app.models.ga4 import FactGa4Traffic
from app.models.gsc import FactGscPage, FactGscQueryPage
from app.models.llm_visibility import ClientLlmSettings
from app.models.seranking import FactSerCompetitorKeyword
from app.services.competitors import bare_domain
from app.services.link_gaps import link_gaps
from app.services.page_eligibility import PageType, classify_page_url
from app.services.page_stage import confirmed_stages
from app.services.conversion_stage import resolve as resolve_conversion_stage
from app.services.serp_features import load as load_serp_features
from app.services.triage_signals import MANAGED_CHANNELS

#: The window the traffic and lead facts are read over.
WINDOW_DAYS = 28

#: Sessions a page needs before its rate joins the site median — enough that
#: the rate is not 0/1 or 1/1.
MEDIAN_SESSION_FLOOR = 10

#: Pages needed before a median describes anything.
MIN_PAGES_FOR_MEDIAN = 5

#: Which offers suit a reader at each stage, matching the catalog's own rule.
from app.decisions.catalog import STAGE_FIT  # noqa: E402
from app.decisions.content_gaps import _GENERIC_RELEVANCE_WORDS, content_words

#: Common 3-letter words/industry terms that should not be treated as standalone
#: uncontextualized rival brands solely because a competitor owns `<word>.com`.
_COMMON_SHORT_WORDS = frozenset(
    "air seo pro law tax spa gas oil pet vet car gym diy web app ads pay fit "
    "sun eco lab med art ink ice dog cat bus van cab bed box key map job top "
    "new hot red bay sea sky hub net dev api sdk crm erp roi kpi ppc sem cro "
    "buy now day one all out".split()
)


def rank_offers(
    url: str, stage: str | None, offers: list[ClientConversionPage],
    crawl: dict[str, FactCrawlPageSnapshot],
    confirmed: dict[str, str] | None = None,
) -> tuple[str, ...]:
    """Choose an intent-compatible destination; uncertainty is not a URL tie-break.

    A configured primary is a general fallback, not permission to ignore an
    explicit location/industry mismatch or send TOFU readers to a BOFU form.
    Non-primary destinations require readable page evidence.
    """
    fits = STAGE_FIT.get(stage or "", ())
    source = crawl.get(url)
    source_text = tokens(url + " " + (source.title or "") + " " + " ".join(
        str(section.get("heading") or "") for section in (source.sections or [])
        if isinstance(section, dict) and section.get("level") in (1, 2)
    )) if source else tokens(url)
    source_location = location_tokens(source) if source else set()
    ranked = []
    for offer in offers:
        target = offer.normalized_url
        effective_stage, _ = resolve_conversion_stage(offer, confirmed or {})
        if effective_stage not in fits or page_identity(target) == page_identity(url):
            continue
        snapshot = crawl.get(target)
        readable = bool(snapshot and snapshot.status_code and 200 <= snapshot.status_code < 300
                        and snapshot.sections is not None)
        if (snapshot and not readable) or (not readable and not offer.is_primary):
            continue
        scope_page = snapshot or SimpleNamespace(normalized_url=target, title=offer.label, sections=[])
        scope = location_tokens(scope_page)
        sector = re.search(r'/industries/([^/]+)', urlsplit(target).path)
        audience = tokens(sector.group(1)) if sector else set()
        if (scope and not scope <= source_location) or (audience and not audience <= source_text):
            continue
        # Prefer a matching specialist destination, then the configured primary.
        score = (bool(scope or audience), bool(offer.is_primary))
        ranked.append((score, target))
    if not ranked:
        return ()
    best = max(score for score, _ in ranked)
    winners = {target for score, target in ranked if score == best}
    # Several equally eligible destinations do not justify picking alphabetically.
    return tuple(winners) if len(winners) == 1 else ()


def _clean_brand_token(value: str | None) -> str:
    return " ".join((value or "").replace("\u2019", "'").lower().split())


def _valid_domain_host(raw: str | None) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    domain = (
        bare_domain(text)
        .split("?", 1)[0]
        .split("#", 1)[0]
        .rsplit("@", 1)[-1]
        .removeprefix("www.")
    )
    if not domain or domain.endswith(":"):
        return ""
    host = domain.split(":", 1)[0].strip(".")
    if "." not in host or " " in host or not re.search(r"[a-z0-9]", host):
        return ""
    return host


def brand_terms(client: Client) -> set[str]:
    """What a searcher types when they mean this site rather than the topic.

    The bare domain ("boyselectrical"), the host ("boyselectrical.com") and
    the company name. A query carrying any of them is navigation.
    """
    terms: set[str] = set()
    domain = _valid_domain_host(client.domain)
    if domain:
        terms.add(domain)
        bare = domain.split(".")[0]
        if len(bare) >= 4 or (
            len(bare) == 3
            and bare not in _COMMON_SHORT_WORDS
            and bare not in _GENERIC_RELEVANCE_WORDS
        ):
            terms.add(bare)
        spaced = _clean_brand_token(bare.replace("-", " ").replace("_", " "))
        if len(spaced) >= 4 or (
            len(spaced) == 3
            and spaced not in _COMMON_SHORT_WORDS
            and spaced not in _GENERIC_RELEVANCE_WORDS
        ):
            terms.add(spaced)
    name = _clean_brand_token(client.client_name)
    if len(name) >= 3:
        terms.add(name)
    # Other names the brand is searched by, entered by hand — the name and
    # the domain cannot say that ACCTek is also "acc technical services".
    for alias in client.brand_aliases or ():
        cleaned = _clean_brand_token(str(alias or ""))
        if len(cleaned) >= 3:
            terms.add(cleaned)
    return terms


def effective_brand_terms(db: Session, client: Client) -> set[str]:
    """Client brand terms plus any custom brand name/patterns configured for LLM tracking."""
    terms = brand_terms(client)
    settings = (
        db.query(ClientLlmSettings)
        .filter(ClientLlmSettings.client_id == client.id)
        .first()
    )
    if settings is not None:
        name = _clean_brand_token(settings.brand_name)
        if len(name) >= 3:
            terms.add(name)
        for pattern in settings.brand_patterns or ():
            cleaned = _clean_brand_token(str(pattern or ""))
            if len(cleaned) >= 3:
                terms.add(cleaned)
    return terms


_RIVAL_BRAND_INTENT_RE = re.compile(
    r"\b(?:reviews?|ratings?|complaints?|vs|versus|alternatives?|login|log\s*in|"
    r"signin|sign\s*in|scam|coupons?|promo|promos|pricing|price|hours|phone|"
    r"address|contact|careers?|jobs|salary|portal|support)\b"
)

#: Multi-word geographic places stripped from EMD rival domains before checking
#: whether any remaining token is an unknown brand/surname word.
_GEO_PHRASE_RE = re.compile(
    r"\b(?:"
    r"new york|los angeles|san diego|san jose|san francisco|san antonio|"
    r"san bernardino|san mateo|san marcos|san juan|"
    r"fort worth|ft worth|fort lauderdale|ft lauderdale|fort myers|ft myers|"
    r"fort wayne|ft wayne|fort collins|ft collins|"
    r"tampa bay|palm bay|west palm beach|palm beach|palm coast|palm springs|"
    r"boca raton|coral gables|coral springs|las vegas|salt lake city|salt lake|"
    r"kansas city|oklahoma city|panama city|jersey city|new orleans|baton rouge|el paso|"
    r"santa ana|santa clara|santa barbara|santa rosa|santa fe|santa monica|santa cruz|"
    r"saint louis|st louis|saint petersburg|st petersburg|saint paul|st paul|"
    r"saint augustine|st augustine|"
    r"cape coral|port saint lucie|port st lucie|daytona beach|virginia beach|"
    r"myrtle beach|long beach|huntington beach|miami beach|delray beach|"
    r"pompano beach|boynton beach|vero beach|grand rapids|cedar rapids|"
    r"little rock|sioux falls|west des moines|des moines|ann arbor|green bay|"
    r"colorado springs|corpus christi|key west|winter park|winter haven|"
    r"new haven|altamonte springs|lake worth|chula vista|overland park|"
    r"garden grove|elk grove|orange county|"
    r"north carolina|south carolina|north dakota|south dakota|"
    r"new jersey|new mexico|new hampshire|new england|rhode island|west virginia|"
    r"long island|northern virginia|british columbia|nova scotia|new brunswick|"
    r"united states|united kingdom|"
    r"central florida|south florida|north florida|"
    r"east bay|south bay|bay area|tri state|twin cities|dc metro"
    r")\b"
)

#: Unambiguous geographic tokens stemmed with `content_words()` (excluding
#: surname-cities like henderson, jackson, madison, lincoln, taylor, clark,
#: baker, flint, wilson, grant, franklin, hamilton, scott, kelly, ross).
_GEO_SINGLE_WORDS = content_words(
    "usa us uk canada australia england scotland ireland ontario quebec alberta "
    "alabama alaska arizona arkansas california colorado connecticut delaware florida "
    "georgia hawaii idaho illinois indiana iowa kansas kentucky louisiana maine "
    "maryland massachusetts michigan minnesota mississippi missouri montana nebraska "
    "nevada ohio oklahoma oregon pennsylvania tennessee texas utah vermont virginia "
    "wisconsin wyoming "
    "orlando tampa miami jacksonville sarasota clearwater gainesville tallahassee "
    "pensacola ocala kissimmee bradenton naples lakeland deltona melbourne "
    "syracuse nashville chicago phoenix dallas houston atlanta denver seattle boston "
    "detroit portland philadelphia pittsburgh cleveland cincinnati columbus indianapolis "
    "knoxville memphis louisville baltimore milwaukee albuquerque tucson fresno "
    "sacramento omaha tulsa oakland minneapolis wichita honolulu anaheim anchorage "
    "toledo durham reno buffalo richmond boise spokane tacoma charleston savannah "
    "raleigh charlotte austin brooklyn manhattan queens bronx vegas "
    "toronto vancouver montreal calgary ottawa edmonton winnipeg "
    "sydney brisbane perth adelaide london manchester birmingham leeds glasgow "
    "liverpool bristol edinburgh "
    "county metro statewide nationwide"
)


_FT_GEO_RE = re.compile(r"\bft(?=\s+(?:worth|lauderdale|myers|wayne|collins)\b)")


def _strip_possessives(value: str) -> str:
    no_singular = re.sub(r"(?<=[a-z0-9])['’]s\b", "", value)
    return re.sub(r"(?<=s)['’](?=$|[^a-z0-9])", "", no_singular)


def _normalize_rival_text(value: str | None) -> str:
    lowered = (value or "").lower()
    spaced = re.sub(r"[-_/:.]+", " ", lowered)
    cleaned = _clean_brand_token(_strip_possessives(spaced))
    return _FT_GEO_RE.sub("fort", cleaned)


def rival_vocab_words(text: str | None) -> frozenset[str]:
    """Content words for rival-EMD matching, stripping multi-word geo phrases first."""
    normalized = _normalize_rival_text(text)
    if not normalized:
        return frozenset()
    return content_words(_GEO_PHRASE_RE.sub(" | ", normalized))


_CHROME_PATHS = frozenset(
    {
        "/about",
        "/about-us",
        "/contact",
        "/contact-us",
        "/team",
        "/our-team",
        "/gallery",
        "/photo-gallery",
        "/testimonials",
        "/client-testimonials",
        "/locations",
        "/service-areas",
        "/service-areas-locations",
        "/service-areas-and-locations",
        "/quote",
        "/request-a-quote",
        "/get-a-quote",
        "/careers",
        "/jobs",
        "/privacy",
        "/privacy-policy",
        "/terms",
        "/terms-of-service",
        "/terms-of-use",
        "/cookie-policy",
        "/login",
        "/signin",
        "/sign-in",
        "/home",
    }
)

_CHROME_TITLES = frozenset(
    {
        "home",
        "homepage",
        "home page",
        "about",
        "about us",
        "contact",
        "contact us",
        "team",
        "our team",
        "gallery",
        "photo gallery",
        "testimonials",
        "client testimonials",
        "locations",
        "service areas",
        "service areas & locations",
        "service areas and locations",
        "quote",
        "request a quote",
        "get a quote",
        "careers",
        "jobs",
        "privacy",
        "privacy policy",
        "terms",
        "terms of service",
        "terms of use",
        "cookie policy",
        "login",
        "sign in",
    }
)

_CHROME_LEAF_SEGMENTS = frozenset(p.lstrip("/") for p in _CHROME_PATHS)
_CHROME_ANYWHERE_SEGMENTS = _CHROME_LEAF_SEGMENTS - frozenset(
    {"locations", "service-areas", "home"}
)
_CHROME_PREFIX_RE = re.compile(
    r"^(?:about-us|contact-us|our-team|photo-gallery|client-testimonials|"
    r"request-a-quote|get-a-quote|careers|jobs|privacy-policy|"
    r"terms-of-service|terms-of-use|cookie-policy|login|signin|sign-in)(?:-|$)"
)
_HOME_TITLE_SEGMENTS = frozenset({"home", "homepage", "home page"})
_PAGE_EXT_RE = re.compile(r"\.(?:html?|php|aspx?|jsp)$")


def is_substantive_page(url: str, row: FactCrawlPageSnapshot) -> bool:
    """True when a crawled snapshot represents substantive content rather than site chrome."""
    if (getattr(row, "page_type", None) or "").strip().lower() == PageType.UTILITY.value:
        return False
    if classify_page_url(url).page_type == PageType.UTILITY:
        return False
    path = (urlsplit(url).path or "/").lower().rstrip("/") or "/"
    title = _clean_brand_token(row.title)
    if title in _CHROME_TITLES:
        return False
    segments = [
        _PAGE_EXT_RE.sub("", raw_seg)
        for raw_seg in path.strip("/").split("/")
        if raw_seg
    ]
    if path == "/" or segments == ["index"]:
        if not title:
            return False
        title_segments = [
            _clean_brand_token(seg)
            for seg in re.split(r"[|—–:/]+|\s+-\s*|\s*-\s+", row.title or "")
            if _clean_brand_token(seg)
        ]
        return not any(seg in _HOME_TITLE_SEGMENTS for seg in title_segments)
    if segments and segments[-1] in _CHROME_LEAF_SEGMENTS:
        return False
    if any(seg in _CHROME_ANYWHERE_SEGMENTS or _CHROME_PREFIX_RE.match(seg) for seg in segments):
        return False
    return True


def rival_core_vocab_from_pages(client: Client, pages: dict) -> frozenset[str]:
    """Substantive crawl words plus primary market, stripping multi-word geo phrases."""
    parts: list[str] = []
    for url, row in pages.items():
        if not is_substantive_page(url, row):
            continue
        headings = [
            str(s.get("heading") or "") for s in (row.sections or []) if isinstance(s, dict)
        ]
        parts.extend([row.title or "", urlsplit(url).path, *headings])
    if client.primary_market:
        parts.append(str(client.primary_market))
    return frozenset().union(*(rival_vocab_words(part) for part in parts if part))


def _emd_words_non_brand(term: str, *, allowed_vocab: frozenset[str]) -> bool:
    """True when an EMD spaced phrase contains only known domain or geo tokens."""
    normalized = _normalize_rival_text(term)
    stripped = _GEO_PHRASE_RE.sub(" ", normalized)
    remaining_words = content_words(stripped)
    return not remaining_words or remaining_words <= allowed_vocab


def _rival_domain_term_groups(domains: Iterable[str]) -> tuple[set[str], set[str]]:
    """Return (exact_terms, emd_spaced_terms) derived from competitor domains."""
    exact_terms: set[str] = set()
    emd_spaced_terms: set[str] = set()
    for raw in domains:
        domain = _valid_domain_host(raw)
        if not domain:
            continue
        exact_terms.add(domain)
        bare = domain.split(".")[0]
        if len(bare) >= 4:
            exact_terms.add(bare)
        elif len(bare) == 3:
            emd_spaced_terms.add(bare)
        spaced = _clean_brand_token(bare.replace("-", " ").replace("_", " "))
        if len(spaced) >= 4:
            if spaced == bare:
                exact_terms.add(spaced)
            else:
                emd_spaced_terms.add(spaced)
    return exact_terms, emd_spaced_terms


def rival_brand_terms_for_domains(domains: Iterable[str]) -> set[str]:
    """Brand stems and domain names derived from a collection of competitor domains."""
    exact_terms, emd_spaced_terms = _rival_domain_term_groups(domains)
    return exact_terms | emd_spaced_terms


def rival_brand_term_groups(
    db: Session, client: Client, extra_domains: Iterable[str] = ()
) -> tuple[set[str], set[str]]:
    """Return (exact_terms, emd_spaced_terms) for competitor brand filtering."""
    domains: set[str] = {
        str(d) for d in (client.competitor_domains or ()) if str(d or "").strip()
    }
    domains.update(str(d) for d in extra_domains if str(d or "").strip())
    domains.update(
        str(d)
        for (d,) in db.query(FactSerCompetitorKeyword.competitor_domain)
        .filter(FactSerCompetitorKeyword.client_id == client.id)
        .distinct()
        if str(d or "").strip()
    )
    exact_terms, emd_spaced_terms = _rival_domain_term_groups(domains)

    settings = (
        db.query(ClientLlmSettings)
        .filter(ClientLlmSettings.client_id == client.id)
        .first()
    )
    if settings is not None and isinstance(settings.competitors, dict):
        for comp_domain, info in settings.competitors.items():
            dom_exact, dom_emd = _rival_domain_term_groups((str(comp_domain),))
            exact_terms.update(dom_exact)
            emd_spaced_terms.update(dom_emd)
            if isinstance(info, dict):
                candidates = [info.get("name"), *(info.get("patterns") or ())]
                for raw in candidates:
                    cleaned = _clean_brand_token(str(raw or ""))
                    if len(cleaned) >= 3:
                        exact_terms.add(cleaned)
    emd_spaced_terms -= exact_terms
    return exact_terms, emd_spaced_terms


def rival_brand_terms(
    db: Session, client: Client, extra_domains: Iterable[str] = ()
) -> set[str]:
    """Competitor brand terms from configured domains, DataForSEO rivals, and LLM settings."""
    exact_terms, emd_spaced_terms = rival_brand_term_groups(
        db, client, extra_domains=extra_domains
    )
    return exact_terms | emd_spaced_terms


def is_navigational(query: str | None, terms: set[str]) -> bool:
    text = _clean_brand_token(query)
    if not text or not terms:
        return False
    stripped_text: str | None = None
    for raw in terms:
        term = _clean_brand_token(raw)
        if not term:
            continue
        if re.search(rf"(?:^|[^a-z0-9]){re.escape(term)}(?:'s)?(?=$|[^a-z0-9])", text):
            return True
        if " " in term:
            if stripped_text is None:
                stripped_text = _clean_brand_token(_strip_possessives(text))
            stripped_term = _clean_brand_token(_strip_possessives(term))
            if stripped_term and re.search(
                rf"(?:^|[^a-z0-9]){re.escape(stripped_term)}(?=$|[^a-z0-9])",
                stripped_text,
            ):
                return True
    return False


def is_rival_navigational(
    query: str | None,
    *,
    exact_terms: set[str],
    emd_terms: set[str],
    core_vocab: frozenset[str],
    geo_vocab: frozenset[str] = _GEO_SINGLE_WORDS,
) -> bool:
    """Whether a query targets a rival brand rather than a geo/industry EMD phrase."""
    if is_navigational(query, exact_terms):
        return True
    if not emd_terms:
        return False
    text = _clean_brand_token(query)
    if not text:
        return False
    normalized_text = _normalize_rival_text(text)
    stripped_text = _clean_brand_token(_GEO_PHRASE_RE.sub(" | ", normalized_text))
    has_cue = bool(_RIVAL_BRAND_INTENT_RE.search(normalized_text))
    allowed_vocab = core_vocab | geo_vocab
    for term in emd_terms:
        norm_term = _normalize_rival_text(term)
        if not norm_term:
            continue
        target_text = normalized_text if _GEO_PHRASE_RE.search(norm_term) else stripped_text
        if not is_navigational(target_text, {norm_term}):
            continue
        short_allowed = (
            allowed_vocab | _GENERIC_RELEVANCE_WORDS | _COMMON_SHORT_WORDS
            if " " not in norm_term and len(norm_term) <= 3
            else allowed_vocab
        )
        if _emd_words_non_brand(norm_term, allowed_vocab=short_allowed):
            if has_cue:
                return True
        else:
            return True
    return False


def _missing_features(row, domain: str | None) -> tuple[str, ...]:
    """Features on the SERP that this client does not hold.

    Where DataForSEO named no domain for a feature, it is counted as not
    held: a feature we cannot show the client holding is one to look at, and
    the action says what the evidence is.
    """
    if row is None:
        return ()
    return tuple(
        sorted(f for f in row.item_types if not row.held_by(f, domain or ""))
    )


def is_addressable(url: str | None) -> bool:
    """Whether this names a page somebody could open and change."""
    text = (url or "").strip()
    if not text:
        return False
    return text.startswith("http://") or text.startswith("https://") or text.startswith("/")


def _gsc_pages(db: Session, client_id: UUID, start: date, end: date) -> dict[str, dict]:
    rows = (
        db.query(
            FactGscPage.normalized_url,
            func.coalesce(func.sum(FactGscPage.clicks), 0),
            func.coalesce(func.sum(FactGscPage.impressions), 0),
            # Impression-weighted, because a plain average over days gives a
            # day with four impressions the same say as a day with four
            # hundred.
            func.coalesce(
                func.sum(FactGscPage.average_position * FactGscPage.impressions), 0
            ),
        )
        .filter(
            FactGscPage.client_id == client_id,
            FactGscPage.date >= start,
            FactGscPage.date <= end,
        )
        .group_by(FactGscPage.normalized_url)
        .all()
    )
    out: dict[str, dict] = {}
    for url, clicks, impressions, weighted in rows:
        impressions = float(impressions or 0)
        position = float(weighted or 0) / impressions if impressions else None
        out[url] = {
            "clicks": float(clicks or 0),
            "impressions": impressions,
            "position": position,
        }
    return out


def _top_queries(db: Session, client_id: UUID, start: date, end: date) -> dict[str, str]:
    """The query drawing the most impressions on each page."""
    rows = (
        db.query(
            FactGscQueryPage.normalized_url,
            FactGscQueryPage.query,
            func.coalesce(func.sum(FactGscQueryPage.impressions), 0).label("imp"),
        )
        .filter(
            FactGscQueryPage.client_id == client_id,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= end,
        )
        .group_by(FactGscQueryPage.normalized_url, FactGscQueryPage.query)
        .order_by(FactGscQueryPage.normalized_url, func.sum(FactGscQueryPage.impressions).desc())
        .all()
    )
    best: dict[str, str] = {}
    for url, query, _ in rows:
        best.setdefault(url, query)
    return best


def _query_shifts(
    db: Session,
    client_id: UUID,
    *,
    window: tuple[date, date],
    prior: tuple[date, date],
) -> dict[str, tuple[str, float | None, float | None]]:
    """Per page, the query that lost the most impressions.

    "This page is down" is not a brief. "It is down on *this* term, which
    was averaging 4 and is now 11" is one, and the query grain is the only
    place that answer exists.

    Returns `{url: (query, position_then, position_now)}` for pages where a
    query lost ground. A query that appeared since is not a loss, so only
    terms present in the earlier window are considered.
    """
    def read(start: date, end: date) -> dict[tuple[str, str], tuple[float, float | None]]:
        rows = (
            db.query(
                FactGscQueryPage.normalized_url,
                FactGscQueryPage.query,
                func.coalesce(func.sum(FactGscQueryPage.impressions), 0),
                func.coalesce(
                    func.sum(
                        FactGscQueryPage.average_position * FactGscQueryPage.impressions
                    ),
                    0,
                ),
            )
            .filter(
                FactGscQueryPage.client_id == client_id,
                FactGscQueryPage.date >= start,
                FactGscQueryPage.date <= end,
            )
            .group_by(FactGscQueryPage.normalized_url, FactGscQueryPage.query)
            .all()
        )
        out: dict[tuple[str, str], tuple[float, float | None]] = {}
        for url, query, impressions, weighted in rows:
            impressions = float(impressions or 0)
            if impressions <= 0:
                continue
            out[(url, query)] = (impressions, float(weighted or 0) / impressions)
        return out

    now = read(*window)
    then = read(*prior)

    worst: dict[str, tuple[float, str, float | None, float | None]] = {}
    for (url, query), (prior_impressions, prior_position) in then.items():
        current_impressions, current_position = now.get((url, query), (0.0, None))
        lost = prior_impressions - current_impressions
        if lost <= 0:
            continue
        best = worst.get(url)
        if best is None or lost > best[0]:
            worst[url] = (lost, query, prior_position, current_position)
    return {url: (q, before, after) for url, (_, q, before, after) in worst.items()}


def _contested_terms(
    db: Session,
    client_id: UUID,
    start: date,
    end: date,
    brand: set[str],
) -> dict[str, tuple[ContestedTerm, ...]]:
    """Per page, the queries it leads on and shares with another page.

    Cannibalisation is read from Search Console alone: one query, two URLs
    of the same site, both drawing it. The keyword matcher cannot say it —
    it stores only matches that clear the client's margin, so every row it
    keeps is by construction an unambiguous one.

    The page leading the query is the candidate, and its rivals ride along.
    A query that names the brand is skipped: two pages answering the
    company's own name is not a split anyone should resolve.
    """
    rows = (
        db.query(
            FactGscQueryPage.query,
            FactGscQueryPage.normalized_url,
            func.coalesce(func.sum(FactGscQueryPage.impressions), 0),
            func.coalesce(
                func.sum(FactGscQueryPage.average_position * FactGscQueryPage.impressions),
                0,
            ),
        )
        .filter(
            FactGscQueryPage.client_id == client_id,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= end,
        )
        .group_by(FactGscQueryPage.query, FactGscQueryPage.normalized_url)
        .all()
    )
    # Protocol/www/query variants are one page, not competing content.
    grouped: dict[tuple[str, str], dict] = {}
    for query, url, impressions, weighted in rows:
        impressions = float(impressions or 0)
        if impressions <= 0 or not is_addressable(url):
            continue
        key = (query, page_identity(url))
        item = grouped.setdefault(key, {"url": url, "impressions": 0.0, "weighted": 0.0})
        item["impressions"] += impressions
        item["weighted"] += float(weighted or 0)
        if url.startswith("https://"):
            item["url"] = url
    by_query: dict[str, list[tuple[str, float, float | None]]] = {}
    for (query, _), item in grouped.items():
        by_query.setdefault(query, []).append(
            (item["url"], item["impressions"], item["weighted"] / item["impressions"])
        )

    found: dict[str, list[ContestedTerm]] = {}
    for query, pages in by_query.items():
        if len(pages) < 2 or is_navigational(query, brand):
            continue
        pages.sort(key=lambda p: (-p[1], p[0]))
        total = sum(p[1] for p in pages)
        if total < CONTESTED_MIN_IMPRESSIONS:
            continue
        lead = pages[0]
        rivals = tuple(
            Rival(url=u, impressions=i, position=pos)
            for u, i, pos in pages[1:]
            if i / total >= CONTESTED_MIN_RIVAL_SHARE
        )
        if not rivals:
            continue
        found.setdefault(lead[0], []).append(
            ContestedTerm(
                term=query,
                total_impressions=total,
                own_impressions=lead[1],
                own_position=lead[2],
                rivals=rivals,
            )
        )
    return {
        url: tuple(sorted(terms, key=lambda t: (-t.total_impressions, t.term)))
        for url, terms in found.items()
    }


def _broken_schema(db: Session, client_id: UUID) -> dict[str, tuple[str, ...]]:
    """Schema blocks that did not parse, per page.

    Markup that is present and invalid is indistinguishable from absent to
    anything reading the page, and is invisible in every report we have.
    """
    out: dict[str, set[str]] = {}
    for url, schema_type, error in (
        db.query(
            FactCrawlPageSchema.normalized_url,
            FactCrawlPageSchema.schema_type,
            FactCrawlPageSchema.parse_error,
        ).filter(
            FactCrawlPageSchema.client_id == client_id,
            FactCrawlPageSchema.parse_error.isnot(None),
        )
    ):
        if not url or not error:
            continue
        out.setdefault(url, set()).add(schema_type or "unnamed block")
    return {url: tuple(sorted(types)) for url, types in out.items()}


def _pages_with_schema(db: Session, client_id: UUID) -> set[str]:
    return {
        url
        for (url,) in db.query(FactCrawlPageSchema.normalized_url)
        .filter(
            FactCrawlPageSchema.client_id == client_id,
            FactCrawlPageSchema.parse_error.is_(None),
        )
        .distinct()
        if url
    }


def _sessions(
    db: Session, client_id: UUID, start: date, end: date
) -> dict[str, tuple[float, float | None]]:
    rows = (
        db.query(
            FactGa4Traffic.normalized_url,
            func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
            func.sum(FactGa4Traffic.engaged_sessions),
        )
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
            FactGa4Traffic.channel.in_(MANAGED_CHANNELS),
        )
        .group_by(FactGa4Traffic.normalized_url)
        .all()
    )
    return {
        url: (
            float(sessions or 0),
            float(engaged) if engaged is not None else None,
        )
        for url, sessions, engaged in rows
    }


def load_page_candidates(
    db: Session, client: Client, *, today: date | None = None
) -> list[PageCandidate]:
    today = today or date.today()
    start = today - timedelta(days=WINDOW_DAYS - 1)
    # The same length of window immediately before, so "down a quarter"
    # compares like with like rather than a month against a fortnight.
    prior_end = start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=WINDOW_DAYS - 1)

    gsc = _gsc_pages(db, client.id, start, today)
    prior = _gsc_pages(db, client.id, prior_start, prior_end)
    queries = _top_queries(db, client.id, start, today)
    shifts = _query_shifts(
        db, client.id, window=(start, today), prior=(prior_start, prior_end)
    )
    sessions = _sessions(db, client.id, start, today)
    brand = brand_terms(client)
    contested = _contested_terms(db, client.id, start, today, brand)
    stages = confirmed_stages(db, client.id)
    # Read, never pulled: a page view that spends credits is one somebody
    # will refresh. `python -m app.pull_serp_features --apply` does the
    # spending, deliberately.
    serp = load_serp_features(db, client, today=today)

    newest_crawl = (
        db.query(func.max(FactCrawlPageSnapshot.snapshot_date))
        .filter(FactCrawlPageSnapshot.client_id == client.id,
                FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY)
        .scalar()
    )
    crawl: dict[str, FactCrawlPageSnapshot] = {}
    if newest_crawl:
        crawl = {
            row.normalized_url: row
            for row in db.query(FactCrawlPageSnapshot).filter(
                FactCrawlPageSnapshot.client_id == client.id,
                FactCrawlPageSnapshot.snapshot_date == newest_crawl,
                FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
            )
        }

    # Unknown offer intent is retained as unknown, never a match for every stage.
    broken_schema = _broken_schema(db, client.id)
    with_schema = _pages_with_schema(db, client.id)

    # Links in from a body, not from a menu. The count on the snapshot is
    # the same figure, but a page missing from the newest crawl has none.
    offer_rows = list(db.query(ClientConversionPage).filter(
        ClientConversionPage.client_id == client.id
    ))
    offers = {row.normalized_url: resolve_conversion_stage(row, stages)[0]
              for row in offer_rows if (row.normalized_url or "").strip()}


    # Every in-content, non-template edge from a page to a declared offer.
    routes: dict[str, set[str]] = {}
    if offers:
        for from_url, to_url in (
            db.query(FactCrawlInternalLink.from_url, FactCrawlInternalLink.to_url)
            .filter(
                FactCrawlInternalLink.client_id == client.id,
                FactCrawlInternalLink.to_url.in_(offers),
                FactCrawlInternalLink.in_content.is_(True),
                FactCrawlInternalLink.is_template.is_(False),
            )
            .distinct()
        ):
            # A link to a stageless offer is still a route out; it is
            # recorded as "generic" so L-3 can tell "no route" from "a route
            # to something unlabelled".
            routes.setdefault(from_url, set()).add(offers.get(to_url) or "generic")

    # The site's own median engagement. The floor is low because this is a
    # description of the site, not a test: it only has to keep a page with
    # one session (a rate of 0% or 100%) from dragging the middle. What stops
    # a *candidate* being judged on noise is MIN_SESSIONS_FOR_ENGAGEMENT,
    # which is much higher. At 30 sessions this starved itself — SMA had 109
    # pages with engagement data and four above the floor, so the median came
    # out None and T-3 could never fire for anybody.
    rates = [
        engaged / total
        for total, engaged in sessions.values()
        if engaged is not None and total >= MEDIAN_SESSION_FLOOR
    ]
    median_engagement = (
        statistics.median(rates) if len(rates) >= MIN_PAGES_FOR_MEDIAN else None
    )

    # Donors are only searched for pages the update catalog could act on:
    # drawing demand and short of editorial links. `_link_gaps` is the
    # lever engine's own donor finder — one definition of "should link to".
    from app.decisions.update_catalog import MIN_PRIOR_IMPRESSIONS, THIN_LINKS

    under_linked = {
        url
        for url, row in gsc.items()
        if row["impressions"] >= MIN_PRIOR_IMPRESSIONS
        and (snap := crawl.get(url)) is not None
        and snap.inbound_editorial_links is not None
        and snap.inbound_editorial_links < THIN_LINKS
    }
    donors_by_url = link_gaps(
        db, client.id, period=(start, today), targets=under_linked
    )

    # GA4 reports a landing page it could not resolve as "(not set)", and it
    # arrives with real sessions attached. It reached the candidate list and
    # drew a T-3 telling somebody to rewrite the opening of "(not set)".
    # Anything that is not an address cannot be acted on.
    #
    # The prior window is in the union too: a page that drew nothing this
    # period but drew something last period has not left the site, it has
    # lost all of its demand — the strongest decay signal there is, and the
    # one reading only the current window drops.
    urls = {u for u in (set(gsc) | set(sessions) | set(prior)) if is_addressable(u)}
    out: list[PageCandidate] = []
    for url in sorted(urls):
        page = gsc.get(url, {})
        was = prior.get(url, {})
        position = page.get("position")
        impressions = page.get("impressions", 0.0)
        lost_query, lost_before, lost_after = shifts.get(url, (None, None, None))
        expected = (
            expected_ctr_percent(position, scenario=REFERENCE_SCENARIO) / 100.0 * impressions
            if position is not None and 1 <= position <= 20 and impressions
            else None
        )
        total_sessions, engaged = sessions.get(url, (0.0, None))
        snapshot = crawl.get(url)
        stage = stages.get(url)
        out.append(
            PageCandidate(
                url=url,
                title=snapshot.title if snapshot else None,
                description=snapshot.description if snapshot else None,
                impressions=impressions,
                clicks=page.get("clicks", 0.0),
                position=position,
                expected_clicks=expected,
                top_query=queries.get(url),
                top_query_is_navigational=is_navigational(queries.get(url), brand),
                missing_serp_features=_missing_features(
                    serp.get((queries.get(url) or "").strip().lower()), client.domain
                ),
                serp_pulled=(queries.get(url) or "").strip().lower() in serp,
                sessions=total_sessions,
                engaged_sessions=engaged,
                site_median_engagement=median_engagement,
                stage=stage,
                crawl_readable=bool(snapshot and snapshot.status_code is not None
                    and 200 <= snapshot.status_code < 300 and snapshot.sections is not None),
                linked_offer_stages=frozenset(routes.get(url, set())),
                # Never itself. SMA's declared conversion page is its
                # homepage, so the top lead action told the homepage to add
                # an in-content link to the homepage.
                matched_offers=rank_offers(url, stage, offer_rows, crawl, stages),
                is_conversion_page=url in offers,
                conversion_elements=(
                    snapshot.conversion_elements if snapshot else None
                ),
                prior_impressions=was.get("impressions", 0.0),
                prior_clicks=was.get("clicks", 0.0),
                prior_position=was.get("position"),
                top_lost_query=lost_query,
                top_lost_query_is_navigational=is_navigational(lost_query, brand),
                top_lost_query_prior_position=lost_before,
                top_lost_query_position=lost_after,
                content_updated_on=(
                    snapshot.content_updated_on if snapshot else None
                ),
                content_updated_source=(
                    snapshot.content_updated_source if snapshot else None
                ),
                word_count=snapshot.word_count if snapshot else None,
                inbound_editorial_links=(
                    snapshot.inbound_editorial_links if snapshot else None
                ),
                sections=tuple(snapshot.sections or ()) if snapshot else (),
                faq_questions=(
                    tuple(snapshot.faq_questions or ()) if snapshot else ()
                ),
                broken_schema=broken_schema.get(url, ()),
                has_schema=url in with_schema,
                contested_terms=contested.get(url, ()),
                link_donors=tuple(
                    LinkDonor(
                        url=gap.source_url,
                        anchor=gap.shared_query,
                        clicks=gap.source_clicks,
                        refdomains=gap.source_refdomains,
                    )
                    for gap in donors_by_url.get(url, ())
                    # Two pages that both rank for the site's own name share
                    # a site, not a subject. ACCTek's /contact-us was told to
                    # take links from three pages anchored "acc technical
                    # services" — which is why brands carry aliases.
                    if not is_navigational(gap.shared_query, brand)
                ),
            )
        )
    return out
