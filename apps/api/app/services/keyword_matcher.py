"""Propose the page a term belongs on, by subject rather than by ranking.

The Search Console suggester reads the page Google already shows for a
query. Where it has one it wins — that is an observation, not a guess. But it
can only ever propose a page that already ranks, so after a relaunch it
offers the homepage for everything, and a term that ranks nowhere gets
nothing at all.

This reads what each page is about. Measured against Search Console on live
data: 72.2% top-1 agreement on SMA's high-impression queries, against 32.8%
for the token overlap the engine used. On Element 6 only 36.8% — and that is
the model being honest rather than failing, because Element 6's sixty pages
are all about carbon fibre and sit 0.594 apart on average against SMA's
0.398.

**The margin is the point.** How far the best page beats the runner-up says
whether the model knows or is guessing. On SMA, proposing only above 0.10
covered a third of terms at 98.5% precision. A single global margin would be
too loose for Element 6 and too tight for SMA, so each client's is measured
against its own Search Console pairs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.crawl import FactCrawlPageSnapshot
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerKeyword

logger = logging.getLogger("organiciq.keyword_matcher")

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

#: Used when a client has too few Search Console pairs to measure its own.
#: The midpoint of what the prototype tested, not a tuned number.
DEFAULT_MARGIN = 0.10

#: Below this many pairs a measured margin is noise, so the default stands.
MIN_PAIRS_TO_CALIBRATE = 30

#: What a calibrated margin has to achieve. A proposal somebody has to
#: check is only worth making if it is usually right.
TARGET_PRECISION = 0.90

#: Headings past this are navigation and footers, which every page shares.
MAX_HEADINGS = 12


@dataclass(frozen=True)
class Match:
    keyword: str
    page_url: str
    score: float
    margin: float
    runner_up_url: str | None


def page_text(page: FactCrawlPageSnapshot) -> str:
    """What the model reads: the page's own summary, then its structure.

    Title and description first because they are what the page says it is.
    Stripping headings from SMA moved agreement 72.2% to 71.0%, so they earn
    their place but are not the thing carrying it.
    """
    headings: list[str] = []
    for section in (page.sections or [])[:MAX_HEADINGS]:
        if isinstance(section, dict):
            heading = (section.get("heading") or "").strip()
            if heading:
                headings.append(heading)
    parts = [
        (page.title or "").strip(),
        (page.description or "").strip(),
        " ".join(headings),
        " ".join(str(q) for q in (page.faq_questions or [])[:MAX_HEADINGS]),
    ]
    return " ".join(part for part in parts if part).strip()


_MODEL = None


def _model():
    """The loaded model, kept for the life of the process.

    Building it reads the weights off disk, which one run does three times
    — pages, the terms it calibrates on, and then every term.
    """
    global _MODEL
    if _MODEL is None:
        from app.services.text_embedding import TextEmbedding

        _MODEL = TextEmbedding(MODEL_NAME)
    return _MODEL


def _embed(texts: list[str]):
    """Vectors for a batch, L2-normalised so a dot product is a cosine."""
    import numpy as np

    vectors = np.array(list(_model().embed(texts)), dtype="float32")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def crawled_pages(db: Session, client: Client) -> list[FactCrawlPageSnapshot]:
    """The newest crawl's indexable pages that have something to read."""
    newest = (
        db.query(func.max(FactCrawlPageSnapshot.snapshot_date))
        .filter(FactCrawlPageSnapshot.client_id == client.id)
        .scalar()
    )
    if newest is None:
        return []
    rows = (
        db.query(FactCrawlPageSnapshot)
        .filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.snapshot_date == newest,
            FactCrawlPageSnapshot.indexable.is_(True),
        )
        .all()
    )
    # A page with no title and no headings gives the model nothing, and a
    # vector built from an empty string matches everything equally.
    return [page for page in rows if page_text(page)]


def embed_pages(pages: list[FactCrawlPageSnapshot]):
    """Vectors for the pages, computed once and passed around.

    Calibrating and matching both need them, and embedding 300 pages twice
    is most of the runtime of a job somebody is waiting on.
    """
    return _embed([page_text(page) for page in pages])


def match(
    terms: list[str],
    pages: list[FactCrawlPageSnapshot],
    *,
    page_vectors=None,
) -> list[Match]:
    """The best page for each term, and how far clear of the runner-up."""
    if not terms or len(pages) < 2:
        return []

    page_vectors = embed_pages(pages) if page_vectors is None else page_vectors
    term_vectors = _embed(terms)
    similarity = term_vectors @ page_vectors.T

    out: list[Match] = []
    for index, term in enumerate(terms):
        row = similarity[index]
        order = row.argsort()[::-1]
        best, second = int(order[0]), int(order[1])
        out.append(
            Match(
                keyword=term,
                page_url=pages[best].normalized_url,
                score=float(row[best]),
                margin=float(row[best] - row[second]),
                runner_up_url=pages[second].normalized_url,
            )
        )
    return out


def calibrate(
    db: Session,
    client: Client,
    pages: list[FactCrawlPageSnapshot],
    *,
    today: date | None = None,
    page_vectors=None,
) -> float | None:
    """The margin this client's own data says is trustworthy.

    Search Console reports the page that actually ranks for a query. That is
    not the page that *should* own the term — where a site ranks the wrong
    page the yardstick is wrong too — so this measures "can the model find
    the page this site already uses for this subject", which is exactly what
    a suggestion needs to do.

    Returns None when there are too few pairs to measure, and the caller
    falls back rather than trusting a number from a handful of queries.
    """
    today = today or date.today()
    start = today - timedelta(days=90)
    known = {page.normalized_url for page in pages}

    pairs = (
        db.query(
            FactGscQueryPage.query,
            FactGscQueryPage.normalized_url,
            func.sum(FactGscQueryPage.impressions).label("impressions"),
        )
        .filter(
            FactGscQueryPage.client_id == client.id,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= today,
        )
        .group_by(FactGscQueryPage.query, FactGscQueryPage.normalized_url)
        .order_by(func.sum(FactGscQueryPage.impressions).desc())
        .limit(2000)
        .all()
    )

    # One page per query — the one it draws most impressions on — and only
    # where that page is in the crawl, because anything else is unmatchable
    # by construction rather than wrong.
    truth: dict[str, str] = {}
    for query, url, _ in pairs:
        key = (query or "").strip().lower()
        if key and key not in truth and url in known:
            truth[key] = url
    if len(truth) < MIN_PAIRS_TO_CALIBRATE:
        return None

    terms = list(truth)[:400]
    results = match(terms, pages, page_vectors=page_vectors)

    # The lowest margin at which the model is right often enough. Walking up
    # rather than down, so the answer is the most coverage that clears the
    # bar rather than the safest number.
    for step in range(0, 31):
        threshold = step / 100.0
        proposed = [r for r in results if r.margin >= threshold]
        if len(proposed) < 10:
            break
        correct = sum(1 for r in proposed if r.page_url == truth[r.keyword])
        if correct / len(proposed) >= TARGET_PRECISION:
            return threshold
    return None


def tracked_terms(db: Session, client_id: UUID) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for row in db.query(FactSerKeyword).filter(FactSerKeyword.client_id == client_id):
        term = (row.keyword or "").strip()
        key = term.lower()
        if term and key not in seen:
            seen.add(key)
            out.append(term)
    return out


# ── Running it ──────────────────────────────────────────────────────────────


def refresh_for(
    db: Session, client: Client, *, today: date | None = None
) -> dict[str, int | float | None]:
    """Measure this client's margin, match its terms, store what clears it.

    Only matches above the margin are stored. A proposal the model is not
    sure of is worse than none: somebody has to check every one, and a
    suggestion that is usually wrong teaches people to ignore the column.
    """
    today = today or date.today()
    pages = crawled_pages(db, client)
    terms = tracked_terms(db, client.id)
    if len(pages) < 2 or not terms:
        return {"pages": len(pages), "terms": len(terms), "stored": 0, "margin": None}

    page_vectors = embed_pages(pages)
    measured = calibrate(db, client, pages, today=today, page_vectors=page_vectors)
    margin = measured if measured is not None else DEFAULT_MARGIN
    client.keyword_match_margin = margin

    results = match(terms, pages, page_vectors=page_vectors)
    kept = [r for r in results if r.margin >= margin]

    from app.models.decision import KeywordPageSuggestion

    db.query(KeywordPageSuggestion).filter(
        KeywordPageSuggestion.client_id == client.id
    ).delete(synchronize_session=False)
    for found in kept:
        db.add(
            KeywordPageSuggestion(
                client_id=client.id,
                keyword=found.keyword,
                page_url=found.page_url,
                score=found.score,
                margin=found.margin,
                runner_up_url=found.runner_up_url,
                model=MODEL_NAME,
                computed_on=today,
            )
        )
    db.commit()

    logger.info(
        "%s: %d pages, %d terms, margin %.2f%s, %d proposed",
        client.slug, len(pages), len(terms), margin,
        "" if measured is not None else " (default — too few pairs to measure)",
        len(kept),
    )
    return {
        "pages": len(pages),
        "terms": len(terms),
        "stored": len(kept),
        "margin": margin,
        "measured": measured is not None,
    }


def suggestions_for(db: Session, client_id: UUID) -> dict[str, "KeywordPageSuggestion"]:
    """Stored proposals, keyed on the lowercased term."""
    from app.models.decision import KeywordPageSuggestion

    return {
        (row.keyword or "").strip().lower(): row
        for row in db.query(KeywordPageSuggestion).filter(
            KeywordPageSuggestion.client_id == client_id
        )
    }
