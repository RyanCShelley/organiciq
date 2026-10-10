"""Which landing pages are top of funnel.

L3 asks what share of managed sessions land on a top-of-funnel page with no
route onward. The link graph is stored and the conversion pages are declared;
the stage of the *landing* page was the missing third input, and the URL will
not supply it — `classify_page_url` guesses from fragments, which is what
declared conversion pages exist to stop.

So a model reads what the crawl already holds and proposes; a person confirms.
Only a confirmed stage is read by the engine, exactly as with conversion
definitions and conversion pages. A suggestion is a reading of a page by
something that has never seen this client's business.

**Scope is the point.** L3 needs stages for the landing pages that actually
drew sessions, not for the whole site. For most clients a few dozen pages
carry almost all of the organic traffic, so this asks about those, ordered by
sessions, rather than putting five hundred rows in front of somebody.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.config import ClientPageStage
from app.models.crawl import FactCrawlPageSnapshot
from app.models.ga4 import FactGa4Traffic
from app.services.triage_signals import MANAGED_CHANNELS

logger = logging.getLogger("organiciq.page_stage")

STAGES = ("tofu", "mofu", "bofu")

#: The words the rest of the product uses for these, so the screen and the
#: conversion-pages screen do not name the same thing two ways.
STAGE_LABEL = {
    "tofu": "Early — just learning",
    "mofu": "Comparing options",
    "bofu": "Ready to buy",
}

#: How far back to look for landing pages worth labelling.
WINDOW_DAYS = 90

#: Headings carry most of the signal; past a dozen it is navigation and
#: footers, which say the same thing on every page.
MAX_SECTIONS = 12
MAX_PARAGRAPH_CHARS = 300


@dataclass(frozen=True)
class PageCandidate:
    """One landing page, with what the crawl knows and what it drew."""

    normalized_url: str
    sessions: float
    title: str | None
    description: str | None
    headings: tuple[str, ...]
    first_paragraphs: tuple[str, ...]
    word_count: int

    def as_prompt_block(self) -> dict:
        """What the model is shown. URL included, but it is one signal of
        several — the point of reading the page is not to re-guess from the
        path."""
        outline = [
            {"heading": h, "opens": p}
            for h, p in zip(self.headings, self.first_paragraphs)
        ]
        return {
            "url": self.normalized_url,
            "title": self.title,
            "meta_description": self.description,
            "word_count": self.word_count,
            "outline": outline,
        }


@dataclass(frozen=True)
class Suggestion:
    normalized_url: str
    stage: str
    confidence: str
    rationale: str


def _sections(raw: list | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    headings: list[str] = []
    paragraphs: list[str] = []
    for section in (raw or [])[:MAX_SECTIONS]:
        if not isinstance(section, dict):
            continue
        heading = (section.get("heading") or "").strip()
        if not heading:
            continue
        headings.append(heading)
        paragraphs.append((section.get("first_paragraph") or "").strip()[:MAX_PARAGRAPH_CHARS])
    return tuple(headings), tuple(paragraphs)


def load_candidates(
    db: Session,
    client: Client,
    *,
    today: date | None = None,
    limit: int = 60,
) -> list[PageCandidate]:
    """Landing pages that drew managed sessions, busiest first.

    Only pages the crawl has seen: a page with no title and no headings gives
    a model nothing to read, and a guess made from the URL alone is the thing
    this module exists to avoid.
    """
    today = today or date.today()
    start = today - timedelta(days=WINDOW_DAYS)

    sessions = (
        db.query(
            FactGa4Traffic.normalized_url.label("url"),
            func.sum(FactGa4Traffic.sessions).label("sessions"),
        )
        .filter(
            FactGa4Traffic.client_id == client.id,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= today,
            FactGa4Traffic.channel.in_(MANAGED_CHANNELS),
        )
        .group_by(FactGa4Traffic.normalized_url)
        .subquery()
    )

    newest = (
        db.query(func.max(FactCrawlPageSnapshot.snapshot_date))
        .filter(FactCrawlPageSnapshot.client_id == client.id)
        .scalar()
    )
    if newest is None:
        return []

    rows = (
        db.query(FactCrawlPageSnapshot, sessions.c.sessions)
        .join(sessions, sessions.c.url == FactCrawlPageSnapshot.normalized_url)
        .filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.snapshot_date == newest,
        )
        .order_by(sessions.c.sessions.desc())
        .limit(limit)
        .all()
    )

    out: list[PageCandidate] = []
    for page, session_count in rows:
        headings, paragraphs = _sections(page.sections)
        if not (page.title or headings):
            continue
        out.append(
            PageCandidate(
                normalized_url=page.normalized_url,
                sessions=float(session_count or 0),
                title=page.title,
                description=page.description,
                headings=headings,
                first_paragraphs=paragraphs,
                word_count=page.word_count or 0,
            )
        )
    return out


# ── The classifier ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You label web pages by where their reader is in a buying \
journey, for a B2B/local services SEO tool.

Return one label per page:
- "tofu": the reader is learning. Explainers, guides, definitions, news, \
"what is X", top-of-funnel blog posts. They are not yet shopping.
- "mofu": the reader is comparing. Service and capability pages, \
methodology, case studies, comparisons, pricing explainers. They have a \
problem and are weighing options.
- "bofu": the reader is ready to act. Contact, quote, demo, booking, \
consultation, signup, "get started" pages.

Judge the page by what it is written to do, not by its URL. A page at /blog/ \
that is a sales pitch is mofu; a page at /services/ that only defines a term \
is tofu.

Set confidence to "high" only when the page's own words make the answer \
obvious. Use "low" when the page could reasonably be read two ways — a human \
reviews those, so a hedge is useful and a false "high" is not.

Keep each rationale under 15 words and quote the page, not the URL.

Reply with JSON only: {"pages": [{"url": ..., "stage": ..., \
"confidence": ..., "rationale": ...}]}"""


class StageClassifier(Protocol):
    name: str

    def classify(self, pages: list[PageCandidate]) -> list[Suggestion]: ...


class NotConfigured(RuntimeError):
    """No classifier is wired up, said in terms somebody can act on."""


class AnthropicStageClassifier:
    """Claude, over the public API.

    Chosen over a local embedding model because this is a judgement about what
    a page is *for*, not what it is *about*. Embeddings are good at topic and
    poor at intent: a guide to choosing a contractor and a page selling
    contractor services sit close together in embedding space and on opposite
    ends of this scale.

    The volume makes the cost a rounding error — a few dozen pages per client
    per month, read once and stored.
    """

    def __init__(self, *, api_key: str, model: str, batch_size: int = 20) -> None:
        self.api_key = api_key
        self.model = model
        self.name = model
        self.batch_size = batch_size

    def classify(self, pages: list[PageCandidate]) -> list[Suggestion]:
        out: list[Suggestion] = []
        for start in range(0, len(pages), self.batch_size):
            batch = pages[start : start + self.batch_size]
            out.extend(self._classify_batch(batch))
        return out

    def _classify_batch(self, batch: list[PageCandidate]) -> list[Suggestion]:
        import httpx

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        {"pages": [p.as_prompt_block() for p in batch]},
                        ensure_ascii=False,
                    ),
                }
            ],
        }
        try:
            response = httpx.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                timeout=120.0,
            )
        except httpx.HTTPError as exc:
            raise NotConfigured(f"The model did not answer: {exc}") from exc

        if response.status_code >= 400:
            raise NotConfigured(
                f"The model refused ({response.status_code}): {response.text[:200]}"
            )

        body = response.json()
        text = "".join(
            block.get("text", "")
            for block in body.get("content", [])
            if block.get("type") == "text"
        )
        return _parse_suggestions(text, {p.normalized_url for p in batch})


def _parse_suggestions(text: str, allowed_urls: set[str]) -> list[Suggestion]:
    """Read the model's reply, and drop anything it made up.

    A model that invents a URL, or a stage outside the three, has not given an
    answer about a page we asked about. Dropping it is better than storing a
    suggestion nobody can trace to a page.
    """
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise NotConfigured("The model's reply contained no JSON.")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise NotConfigured("The model's reply was not valid JSON.") from exc

    out: list[Suggestion] = []
    for row in parsed.get("pages") or []:
        url = (row.get("url") or "").strip()
        stage = (row.get("stage") or "").strip().lower()
        if url not in allowed_urls or stage not in STAGES:
            logger.warning("page_stage: dropped %r / %r", url, stage)
            continue
        confidence = (row.get("confidence") or "").strip().lower()
        out.append(
            Suggestion(
                normalized_url=url,
                stage=stage,
                confidence=confidence if confidence in ("high", "medium", "low") else "low",
                rationale=(row.get("rationale") or "").strip()[:500],
            )
        )
    return out


def load_classifier() -> StageClassifier | None:
    key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        return None
    model = (os.getenv("PAGE_STAGE_MODEL") or "claude-haiku-5-5").strip()
    return AnthropicStageClassifier(api_key=key, model=model)


def configured() -> bool:
    return load_classifier() is not None


# ── Persistence ─────────────────────────────────────────────────────────────


def save_suggestions(
    db: Session,
    client: Client,
    suggestions: list[Suggestion],
    *,
    model: str,
) -> int:
    """Store what the model said, without touching what anybody confirmed.

    A re-run of the suggester must not quietly revise a stage a person already
    agreed to — that would make the confirmed set drift under them.
    """
    now = datetime.now(timezone.utc)
    existing = {
        row.normalized_url: row
        for row in db.query(ClientPageStage).filter(
            ClientPageStage.client_id == client.id
        )
    }
    written = 0
    for suggestion in suggestions:
        row = existing.get(suggestion.normalized_url)
        if row is None:
            row = ClientPageStage(
                client_id=client.id, normalized_url=suggestion.normalized_url
            )
            db.add(row)
        row.suggested_stage = suggestion.stage
        row.confidence = suggestion.confidence
        row.rationale = suggestion.rationale
        row.model = model[:64]
        row.suggested_at = now
        written += 1
    db.commit()
    return written


def confirm(
    db: Session,
    client: Client,
    entries: list[tuple[str, str]],
    *,
    user_id: UUID | None,
) -> int:
    """Record the stages somebody agreed to."""
    now = datetime.now(timezone.utc)
    existing = {
        row.normalized_url: row
        for row in db.query(ClientPageStage).filter(
            ClientPageStage.client_id == client.id
        )
    }
    written = 0
    for url, stage in entries:
        url = (url or "").strip()
        stage = (stage or "").strip().lower()
        if not url or stage not in STAGES:
            continue
        row = existing.get(url)
        if row is None:
            row = ClientPageStage(client_id=client.id, normalized_url=url)
            db.add(row)
        row.stage = stage
        row.confirmed_at = now
        row.confirmed_by = user_id
        written += 1
    db.commit()
    return written


def confirmed_stages(db: Session, client_id: UUID) -> dict[str, str]:
    """The stages the engine is allowed to read."""
    return {
        row.normalized_url: row.stage
        for row in db.query(ClientPageStage).filter(
            ClientPageStage.client_id == client_id,
            ClientPageStage.confirmed_at.isnot(None),
            ClientPageStage.stage.isnot(None),
        )
    }
