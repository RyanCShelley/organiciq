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

import statistics
from datetime import date, timedelta
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.ctr_curve import expected_ctr_percent
from app.decisions.page_targets import LinkDonor, PageCandidate
from app.models.client import Client
from app.models.config import ClientConversionPage
from app.models.crawl import (
    FactCrawlInternalLink,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from app.models.ga4 import FactGa4Traffic
from app.models.gsc import FactGscPage, FactGscQueryPage
from app.services.lever_engine import _link_gaps
from app.services.page_stage import confirmed_stages
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


def brand_terms(client: Client) -> set[str]:
    """What a searcher types when they mean this site rather than the topic.

    The bare domain ("boyselectrical"), the host ("boyselectrical.com") and
    the company name. A query carrying any of them is navigation.
    """
    terms: set[str] = set()
    domain = (client.domain or "").strip().lower()
    if domain:
        if "://" in domain:
            domain = urlsplit(domain).netloc or domain
        domain = domain.split("/")[0].removeprefix("www.")
        if domain:
            terms.add(domain)
            bare = domain.split(".")[0]
            if len(bare) > 3:
                terms.add(bare)
    name = (client.client_name or "").strip().lower()
    if len(name) > 3:
        terms.add(name)
    return terms


def is_navigational(query: str | None, terms: set[str]) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return False
    return any(term in text for term in terms)


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
    stages = confirmed_stages(db, client.id)
    brand = brand_terms(client)
    # Read, never pulled: a page view that spends credits is one somebody
    # will refresh. `python -m app.pull_serp_features --apply` does the
    # spending, deliberately.
    serp = load_serp_features(db, client, today=today)

    newest_crawl = (
        db.query(func.max(FactCrawlPageSnapshot.snapshot_date))
        .filter(FactCrawlPageSnapshot.client_id == client.id)
        .scalar()
    )
    crawl: dict[str, FactCrawlPageSnapshot] = {}
    if newest_crawl:
        crawl = {
            row.normalized_url: row
            for row in db.query(FactCrawlPageSnapshot).filter(
                FactCrawlPageSnapshot.client_id == client.id,
                FactCrawlPageSnapshot.snapshot_date == newest_crawl,
            )
        }

    # An offer with no declared stage is the generic one and suits any
    # reader — which is what `ClientConversionPage` already assumes when it
    # falls back to the primary offer. Treating a null stage as "matches
    # nothing" meant that for every client in the warehouse, all of whose
    # conversion pages have a null stage, no lead action could ever fire.
    broken_schema = _broken_schema(db, client.id)
    with_schema = _pages_with_schema(db, client.id)

    # Links in from a body, not from a menu. The count on the snapshot is
    # the same figure, but a page missing from the newest crawl has none.
    offers = {
        (row.normalized_url or "").strip(): (row.stage or "").strip().lower() or None
        for row in db.query(ClientConversionPage).filter(
            ClientConversionPage.client_id == client.id
        )
        if (row.normalized_url or "").strip()
    }

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
    donors_by_url = _link_gaps(
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
            expected_ctr_percent(position) / 100.0 * impressions
            if position and impressions
            else None
        )
        total_sessions, engaged = sessions.get(url, (0.0, None))
        snapshot = crawl.get(url)
        stage = stages.get(url)
        fits = STAGE_FIT.get(stage or "", ())
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
                linked_offer_stages=frozenset(routes.get(url, set())),
                # Never itself. SMA's declared conversion page is its
                # homepage, so the top lead action told the homepage to add
                # an in-content link to the homepage.
                matched_offers=tuple(
                    sorted(
                        u
                        for u, s in offers.items()
                        if (s is None or s in fits) and u != url
                    )
                ),
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
                    # services".
                    if not is_navigational(gap.shared_query, brand)
                ),
            )
        )
    return out
