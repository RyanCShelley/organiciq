"""Proposing a page for a term by subject rather than by ranking.

The Search Console suggester can only ever offer a page that already ranks,
so after a relaunch it offers the homepage for everything and a term that
ranks nowhere gets nothing. This reads what each page is about.

The model is stubbed here. What is worth testing is not whether MiniLM
embeds well — the prototype measured that against live data — but the
decisions around it: what the model is shown, when a proposal is withheld,
and how the margin is chosen.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.gsc import FactGscQueryPage
from app.services import keyword_matcher as km

TODAY = date(2026, 10, 12)


def _page(db: Session, client: Client, url: str, **kw):
    row = FactCrawlPageSnapshot(
        client_id=client.id,
        source=CRAWL_SOURCE_FIRST_PARTY,
        snapshot_date=TODAY,
        raw_url=url,
        normalized_url=url,
        indexable=kw.pop("indexable", True),
        title=kw.pop("title", f"Title {url}"),
        word_count=400,
        **kw,
    )
    db.add(row)
    return row


def _stub_embeddings(monkeypatch, vectors: dict[str, list[float]]):
    """Each text is embedded as whatever the map says, normalised."""

    def fake(texts: list[str]):
        out = []
        for text in texts:
            key = next((k for k in vectors if k in text), None)
            out.append(vectors[key] if key else [0.0, 0.0, 1.0])
        arr = np.array(out, dtype="float32")
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms

    monkeypatch.setattr(km, "_embed", fake)


# ── What the model is shown ─────────────────────────────────────────────────


def test_the_page_text_is_the_summary_then_the_structure():
    page = FactCrawlPageSnapshot(
        normalized_url="/a",
        title="Local SEO services",
        description="Win the job locally",
        sections=[{"heading": "Our approach"}, {"heading": "Reviews"}],
        faq_questions=["How long does local SEO take?"],
    )
    text = km.page_text(page)
    assert text.startswith("Local SEO services Win the job locally")
    assert "Our approach" in text and "How long does local SEO take?" in text


def test_a_page_with_nothing_to_read_is_not_a_candidate(db: Session, client_a: Client):
    # A vector built from an empty string matches everything equally, so an
    # empty page would win ties against real ones.
    _page(db, client_a, "https://x.test/blank", title=None)
    _page(db, client_a, "https://x.test/real", title="Local SEO services")
    db.commit()
    assert [p.normalized_url for p in km.crawled_pages(db, client_a)] == [
        "https://x.test/real"
    ]


def test_a_noindex_page_is_not_a_candidate(db: Session, client_a: Client):
    _page(db, client_a, "https://x.test/hidden", indexable=False)
    db.commit()
    assert km.crawled_pages(db, client_a) == []


# ── Matching ────────────────────────────────────────────────────────────────


def test_it_proposes_the_nearest_page_and_says_how_clear_it_was(monkeypatch):
    _stub_embeddings(
        monkeypatch,
        {
            "local seo": [1.0, 0.0, 0.0],
            "Local": [0.95, 0.1, 0.0],
            "Content": [0.2, 1.0, 0.0],
        },
    )
    pages = [
        FactCrawlPageSnapshot(normalized_url="/local", title="Local SEO services"),
        FactCrawlPageSnapshot(normalized_url="/content", title="Content marketing"),
    ]
    found = km.match(["local seo"], pages)
    assert len(found) == 1
    assert found[0].page_url == "/local"
    assert found[0].runner_up_url == "/content"
    assert found[0].margin > 0


def test_one_page_cannot_be_matched_against():
    # There is no runner-up, so there is no margin, so there is no way to
    # know whether the model is sure.
    assert km.match(["x"], [FactCrawlPageSnapshot(normalized_url="/only")]) == []
    assert km.match([], []) == []


# ── The margin ──────────────────────────────────────────────────────────────


def test_too_few_pairs_to_measure_returns_none(db: Session, client_a: Client, monkeypatch):
    """A margin measured on a handful of queries is a number, not evidence.

    The caller falls back to the default rather than trusting it.
    """
    _stub_embeddings(monkeypatch, {})
    pages = [FactCrawlPageSnapshot(normalized_url="/a", title="A")]
    for index in range(5):
        db.add(
            FactGscQueryPage(
                client_id=client_a.id,
                date=TODAY,
                query=f"term {index}",
                raw_url="/a",
                normalized_url="/a",
                impressions=100,
                clicks=1,
            )
        )
    db.commit()
    assert km.calibrate(db, client_a, pages, today=TODAY) is None


def test_the_margin_is_measured_against_the_clients_own_pairs(
    db: Session, client_a: Client, monkeypatch
):
    """SMA's pages sit 0.398 apart on average and Element 6's 0.594, so one
    global margin would be too loose for one and too tight for the other."""
    # Half the terms match their page exactly; half are ambiguous.
    _stub_embeddings(
        monkeypatch,
        {
            "sure": [1.0, 0.0, 0.0],
            "Sure page": [1.0, 0.0, 0.0],
            "Other page": [0.0, 1.0, 0.0],
        },
    )
    pages = [
        FactCrawlPageSnapshot(normalized_url="/sure", title="Sure page"),
        FactCrawlPageSnapshot(normalized_url="/other", title="Other page"),
    ]
    for index in range(40):
        db.add(
            FactGscQueryPage(
                client_id=client_a.id,
                date=TODAY,
                query=f"sure {index}",
                raw_url="/sure",
                normalized_url="/sure",
                impressions=100,
                clicks=1,
            )
        )
    db.commit()

    margin = km.calibrate(db, client_a, pages, today=TODAY)
    # Every proposal is right, so the lowest threshold clears the bar and
    # the most terms get a suggestion.
    assert margin == 0.0


@pytest.mark.parametrize("value", [km.DEFAULT_MARGIN, km.TARGET_PRECISION])
def test_the_constants_are_what_the_prototype_measured(value: float):
    # 0.10 covered a third of SMA's terms at 98.5% precision; the precision
    # bar is what a proposal somebody has to check is worth.
    assert 0 < value <= 1
