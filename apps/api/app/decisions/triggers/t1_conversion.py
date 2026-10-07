"""T1 — the page takes traffic and does not convert it.

Two rules, checked in order, first match wins. There is no fallback: a
page that enters the gate and matches neither is recorded as
`no_rule_matched` and nothing is emitted, because a generic finding on a
page we could not diagnose is the thing this rebuild exists to remove.

The entry gate is relative, not absolute. A fixed session floor was tried
and would have emptied the trigger: SMA has six pages above thirty
sessions in a month and two above a hundred. "High traffic" has to mean
high for this client, so it is the top quartile of their own eligible
pages with a floor underneath it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.decisions.prescription import Prescription, Step
from app.decisions.triggers.coverage import SkipReason


@dataclass(frozen=True)
class Offer:
    url: str
    label: str
    stage: str | None = None


@dataclass(frozen=True)
class PageSignals:
    url: str
    sessions: float
    engaged_sessions: float
    page_stage: str | None
    #: None when the client has no crawl, which is not the same as a page
    #: with no links.
    in_content_links_to_offers: int | None = None
    in_crawl: bool = True


@dataclass
class T1Inputs:
    pages: list[PageSignals]
    offers: list[Offer] = field(default_factory=list)
    has_crawl: bool = False

    @property
    def by_url(self) -> dict[str, PageSignals]:
        return {page.url: page for page in self.pages}


def eligible_gate(
    pages: list[PageSignals], *, min_sessions: float, top_share: float
) -> list[PageSignals]:
    """The client's own busiest pages, not a number from another client.

    Ranked by sessions, floored, then cut to the top share. On a six-page
    site that admits two; on a site with three eligible pages, one. Never
    more than the share, however large the site.
    """
    qualifying = sorted(
        (page for page in pages if page.sessions >= min_sessions),
        key=lambda page: -page.sessions,
    )
    if not qualifying:
        return []
    keep = max(1, math.ceil(len(qualifying) * top_share))
    return qualifying[:keep]


def baseline_bounce(pages: list[PageSignals], *, exclude: str) -> tuple[float | None, float]:
    """The site's bounce rate, weighted by sessions, without this page.

    Excluding the page under test matters most on the small sites this
    has to work for: with six eligible pages, a page contributing a third
    of the sessions is a third of the bar it is being measured against.
    """
    sessions = sum(p.sessions for p in pages if p.url != exclude)
    engaged = sum(p.engaged_sessions for p in pages if p.url != exclude)
    if sessions <= 0:
        return None, 0.0
    return 1.0 - (engaged / sessions), sessions


def pick_offer(offers: list[Offer], page_stage: str | None) -> Offer | None:
    """The offer that matches where the reader is, else the primary one."""
    if not offers:
        return None
    if page_stage:
        for offer in offers:
            if offer.stage == page_stage:
                return offer
    for offer in offers:
        if offer.stage is None and getattr(offer, "is_primary", False):
            return offer
    return offers[0]


def classify_page(
    page: PageSignals,
    inputs: T1Inputs,
    *,
    thresholds: dict,
) -> tuple[Prescription | None, SkipReason | None, str | None]:
    """(prescription, skip reason, rule id). Exactly one is not None."""
    bounce_multiple = float(thresholds.get("t1_bounce_multiple", 1.2))
    baseline_min = float(thresholds.get("t1_baseline_min_sessions", 200))

    # ── 1a: the page loses them before it says anything ──
    baseline, baseline_sessions = baseline_bounce(inputs.pages, exclude=page.url)
    if baseline is None or baseline_sessions < baseline_min:
        skip_1a: SkipReason | None = SkipReason.INSUFFICIENT_BASELINE
    else:
        skip_1a = None
        bounce = 1.0 - (page.engaged_sessions / page.sessions if page.sessions else 0.0)
        # Rounded before comparing: a page at exactly the bar should not
        # fire, and 0.24 > 0.23999999999999994 is the kind of true that
        # makes a threshold mean nothing.
        if round(bounce, 4) > round(baseline * bounce_multiple, 4):
            return (
                Prescription(
                    cause="conversion_proof_missing",
                    evidence={
                        "bounce_pct": round(bounce * 100, 1),
                        "baseline_bounce_pct": round(baseline * 100, 1),
                        "baseline_sessions": round(baseline_sessions),
                        "baseline": "site_session_weighted_excluding_page",
                        "sessions": round(page.sessions),
                    },
                    steps=[
                        Step(
                            f"Rewrite the first 120 words of {page.url} so proof leads",
                            target=page.url,
                            detail="A named result, a number, or a credential, before any "
                            f"explanation. {bounce * 100:.0f}% of visitors leave without "
                            f"engaging, against {baseline * 100:.0f}% across the site.",
                        )
                    ],
                    expected_impact="",
                    verify_metric="page_lead_rate",
                    verify_after_days=28,
                ),
                None,
                "1a",
            )

    # ── 1b: nothing on the page asks for the next step ──
    # Where both rules are unrunnable, 1a's reason is reported: it is the
    # rule that was reached first and the more informative of the two.
    if not inputs.has_crawl:
        return None, skip_1a or SkipReason.CRAWL_NOT_READY, None
    if not page.in_crawl:
        return None, skip_1a or SkipReason.PAGE_NOT_CRAWLED, None
    if page.in_content_links_to_offers == 0:
        offer = pick_offer(inputs.offers, page.page_stage)
        if offer is None:
            # No declared pages and the fallback patterns matched nothing.
            # Inventing an offer here would put a URL in front of someone
            # that the client never agreed is where the lead goes.
            return (
                Prescription(
                    cause="conversion_offer_missing",
                    evidence={"sessions": round(page.sessions), "offer": None},
                    steps=[
                        Step(
                            f"Choose the offer for {page.url}: declare a conversion page "
                            "for this client",
                            target=page.url,
                            detail="Nothing on the site is marked as where a lead goes, "
                            "and the URL patterns matched nothing either.",
                            human=True,
                        )
                    ],
                    expected_impact="",
                    verify_metric="page_lead_rate",
                    verify_after_days=28,
                ),
                None,
                "1b",
            )
        return (
            Prescription(
                cause="conversion_cta_missing",
                evidence={
                    "sessions": round(page.sessions),
                    "offer_url": offer.url,
                    "offer_label": offer.label,
                    "offer_stage": offer.stage,
                    "page_stage": page.page_stage,
                },
                steps=[
                    Step(
                        f"Add a CTA link to {offer.label} in the section where "
                        f"{page.url} first demonstrates value",
                        target=offer.url,
                        detail="No in-content link from this page reaches a conversion "
                        "page today. Navigation and footer links do not count: they are "
                        "on every page and say nothing about this one.",
                    )
                ],
                expected_impact="",
                verify_metric="page_lead_rate",
                verify_after_days=28,
            ),
            None,
            "1b",
        )

    # Entered the gate, matched nothing. Recorded, not papered over.
    return None, skip_1a or SkipReason.NO_RULE_MATCHED, None
