"""Find the tracked terms the site has no page for, and say why the rest were not.

Read for the content allowance's pool. The count of what was excluded and
why travels with the result, because a short plan has to show its shortfall:
"0 gaps" is an answer only if it says the other 64 terms each have a page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.decisions.content_gaps import (
    COVERED_SHARE,
    MIN_VOLUME,
    NearPage,
    TermGap,
    content_words,
    fold_variants,
    is_noise_query,
)
from app.models.client import Client
from app.models.crawl import FactCrawlPageSnapshot
from app.models.decision import KeywordTarget
from app.models.seranking import FactSerKeyword, FactSerKeywordMetric
from app.models.watch_target import WatchTarget
from app.services.page_signals import (
    effective_brand_terms,
    is_navigational,
    is_rival_navigational,
    rival_brand_term_groups,
    rival_core_vocab_from_pages,
)
from app.services.serp_features import load as load_serp_features

#: Indexable pages a crawl must have returned before its silence means
#: anything. Fourteen clients have a crawl of zero or one page — a site the
#: crawler could not read — and "no page carries this term" about a crawl
#: that saw nothing is not a finding.
MIN_CRAWLED_PAGES = 10

#: How many close pages the brief names to link from.
NEAREST_PAGES = 3


@dataclass(frozen=True)
class GapScan:
    gaps: list[TermGap]
    #: Why each tracked term was or was not a gap, in counts. Rendered in the
    #: record so an empty pool can say what it checked.
    summary: dict[str, int] = field(default_factory=dict)
    #: Set when the scan could not run at all.
    blocked: str | None = None
    #: Eligible unpriced GSC candidates awaiting volume data (never already rejected in FactSerKeywordMetric).
    unpriced: tuple[Any, ...] = ()

    def explain_empty(self) -> str:
        if self.blocked:
            return self.blocked
        s = self.summary
        tracked = s.get("tracked", 0)
        if not tracked:
            return "No term is tracked for this client, so there is nothing to find a page for."
        parts = []
        if s.get("excluded"):
            parts.append(f"{s['excluded']} excluded")
        if s.get("mapped"):
            parts.append(f"{s['mapped']} mapped to a page")
        if s.get("covered"):
            parts.append(f"{s['covered']} already covered by a page's title, URL or headings")
        if s.get("ranking"):
            parts.append(f"{s['ranking']} already ranking")
        if s.get("brand"):
            parts.append(f"{s['brand']} brand queries")
        if s.get("noise"):
            parts.append(f"{s['noise']} navigational or utility noise")
        if s.get("no_metrics"):
            parts.append(f"{s['no_metrics']} without volume and difficulty")
        if s.get("small"):
            parts.append(f"{s['small']} under the volume floor")
        detail = f" ({', '.join(parts)})" if parts else ""
        return f"Every one of the {tracked} tracked terms has a page or was set aside{detail}."


def scan_term_gaps(db: Session, client: Client) -> GapScan:
    pages = {
        row.normalized_url: row
        for row in db.query(FactCrawlPageSnapshot).filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.indexable.is_(True),
        )
    }
    if len(pages) < MIN_CRAWLED_PAGES:
        return GapScan(
            gaps=[],
            blocked=(
                f"The crawl found {len(pages)} indexable "
                f"page{'' if len(pages) == 1 else 's'}, too few to say a term has no "
                "page. Fix the crawl before planning new content."
            ),
        )

    page_words: dict[str, frozenset[str]] = {}
    for url, row in pages.items():
        headings = [
            str(s.get("heading") or "")
            for s in (row.sections or [])
            if isinstance(s, dict)
        ]
        # The path only: the scheme and host are on every page and would make
        # "com" or the client's own name look covered everywhere.
        page_words[url] = content_words(
            " ".join([row.title or "", urlsplit(url).path, *headings])
        )

    tracked: dict[str, FactSerKeyword] = {}
    for row in db.query(FactSerKeyword).filter(FactSerKeyword.client_id == client.id, FactSerKeyword.is_tracked.is_(True)):
        key = " ".join((row.keyword or "").lower().split())
        held = tracked.get(key)
        if key and (held is None or (row.checked_at or 0) > (held.checked_at or 0)):
            tracked[key] = row
    metrics = {
        " ".join((row.keyword or "").lower().split()): row
        for row in db.query(FactSerKeywordMetric).filter(
            FactSerKeywordMetric.client_id == client.id
        )
    }
    targets = {
        " ".join((row.keyword or "").lower().split()): row
        for row in db.query(KeywordTarget).filter(
            KeywordTarget.client_id == client.id,
            KeywordTarget.source.in_(("confirmed", "auto")),
        )
    }
    serp = load_serp_features(db, client)
    brand = effective_brand_terms(db, client)
    exact_rival, emd_rival = rival_brand_term_groups(db, client)
    everywhere = frozenset().union(*page_words.values()) if page_words else frozenset()
    rival_core_vocab = rival_core_vocab_from_pages(client, pages)

    summary = {
        "tracked": len(tracked), "excluded": 0, "mapped": 0, "brand": 0, "noise": 0,
        "ranking": 0, "no_metrics": 0, "small": 0, "covered": 0, "gaps": 0,
        "pages_searched": len(pages),
    }
    gaps: list[TermGap] = []
    excluded_terms: set[str] = set()
    for (text,) in db.query(WatchTarget.text).filter(
        WatchTarget.client_id == client.id,
        WatchTarget.kind == "keyword",
        WatchTarget.state == "excluded",
    ):
        norm = " ".join((text or "").lower().split())
        if norm:
            excluded_terms.add(norm)
        punct_norm = " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())
        if punct_norm:
            excluded_terms.add(punct_norm)
    for term, row in tracked.items():
        punct_term = " ".join(re.sub(r"[^a-z0-9]+", " ", term.lower()).split())
        if term in excluded_terms or punct_term in excluded_terms:
            summary["excluded"] += 1
            continue
        target = targets.get(term)
        recorded_no_page = target is not None and not (target.target_url or "").strip()
        if target is not None and not recorded_no_page:
            summary["mapped"] += 1
            continue
        if is_navigational(term, brand) or is_rival_navigational(
            term, exact_terms=exact_rival, emd_terms=emd_rival, core_vocab=rival_core_vocab
        ):
            summary["brand"] += 1
            continue
        if is_noise_query(term, strict_platforms=False):
            summary["noise"] += 1
            continue
        position = float(row.current_position or 0)
        if row.ranking_url and 0 < position <= 100:
            summary["ranking"] += 1
            continue
        metric = metrics.get(term)
        volume = float(metric.volume) if metric and metric.volume else float(row.volume or 0)
        if metric is None or metric.difficulty is None or volume <= 0:
            summary["no_metrics"] += 1
            continue
        if volume < MIN_VOLUME:
            summary["small"] += 1
            continue

        words = content_words(term)
        if not words:
            summary["noise"] = summary.get("noise", 0) + 1
            continue
        absent = tuple(sorted(words - everywhere))
        best = max((len(words & pw) / len(words) for pw in page_words.values()), default=0.0) if words else 0.0
        # A word the site never uses settles it: whatever else matches, the
        # page the term needs is the one that says it. Otherwise the term is
        # covered when a single page carries most of its words.
        if not recorded_no_page and not absent and best >= COVERED_SHARE:
            summary["covered"] += 1
            continue

        nearest = sorted(
            (
                (len(words & pw), url)
                for url, pw in page_words.items()
                if words & pw
            ),
            key=lambda pair: (-pair[0], pair[1]),
        )[:NEAREST_PAGES]
        features = tuple(sorted(serp[term].item_types)) if term in serp else ()
        gaps.append(
            TermGap(
                term=term,
                volume=volume,
                difficulty=float(metric.difficulty),
                intents=tuple(metric.intents or ()),
                nearest=tuple(
                    NearPage(
                        url=url,
                        title=pages[url].title,
                        shared=tuple(sorted(words & page_words[url])),
                    )
                    for _, url in nearest
                ),
                serp_features=features,
                recorded_no_page=recorded_no_page,
                pages_searched=len(pages),
                absent_words=absent,
                best_overlap=best,
            )
        )

    folded = fold_variants(gaps)
    summary["gaps"] = len(folded)
    return GapScan(gaps=folded, summary=summary)
