"""Pull the SERP feature list for a client's priority terms, and read it back.

Every call is billed, so which queries get pulled is a decision this module
makes deliberately and narrowly: the terms the engine would act on, capped,
newest pull wins. A run reads what was stored and never pulls — a page view
that spends credits is a page view somebody will refresh.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.integrations import dataforseo
from app.models.client import Client
from app.models.decision import KeywordTarget
from app.models.seranking import FactSerKeyword, FactSerpFeature

logger = logging.getLogger("organiciq.serp_features")

#: The spec's figure: the top targets per client, monthly.
DEFAULT_LIMIT = 20

#: A SERP older than this is not evidence about today's SERP.
STALE_AFTER_DAYS = 45


@dataclass(frozen=True)
class SerpRow:
    keyword: str
    pulled_on: date
    item_types: frozenset[str]
    holders: dict[str, tuple[str, ...]]

    def present(self, feature: str) -> bool:
        return feature in self.item_types

    def held_by(self, feature: str, domain: str) -> bool:
        target = (domain or "").strip().lower().removeprefix("www.")
        if not target:
            return False
        return any(target in h for h in self.holders.get(feature, ()))


def terms_to_pull(db: Session, client: Client, *, limit: int = DEFAULT_LIMIT) -> list[str]:
    """The terms worth spending a credit on.

    Declared targets first — those are the ones somebody said matter — then
    tracked terms by volume. Capped, because this is money.
    """
    seen: set[str] = set()
    out: list[str] = []

    for row in (
        db.query(KeywordTarget)
        .filter(KeywordTarget.client_id == client.id)
        .order_by(KeywordTarget.keyword)
    ):
        term = (row.keyword or "").strip()
        key = term.lower()
        if term and key not in seen:
            seen.add(key)
            out.append(term)
        if len(out) >= limit:
            return out

    for row in (
        db.query(FactSerKeyword)
        .filter(FactSerKeyword.client_id == client.id)
        .order_by(FactSerKeyword.volume.desc().nullslast())
    ):
        term = (row.keyword or "").strip()
        key = term.lower()
        if term and key not in seen:
            seen.add(key)
            out.append(term)
        if len(out) >= limit:
            break
    return out


def pull(
    db: Session,
    client: Client,
    *,
    limit: int = DEFAULT_LIMIT,
    today: date | None = None,
    client_http=None,
) -> tuple[int, list[str]]:
    """Pull and store. Returns how many landed, and the failures."""
    today = today or date.today()
    pulled = 0
    failures: list[str] = []

    for term in terms_to_pull(db, client, limit=limit):
        existing = (
            db.query(FactSerpFeature)
            .filter(
                FactSerpFeature.client_id == client.id,
                FactSerpFeature.keyword == term,
                FactSerpFeature.pulled_on == today,
            )
            .one_or_none()
        )
        if existing is not None:
            # Already paid for today.
            continue
        try:
            features = dataforseo.fetch(term, client=client_http)
        except dataforseo.DataForSeoAuthError:
            # Will not come right on the next keyword. Stop rather than
            # collect the same failure once per term.
            db.commit()
            raise
        except dataforseo.DataForSeoError as exc:
            failures.append(f"{term}: {exc}")
            continue
        db.add(
            FactSerpFeature(
                client_id=client.id,
                pulled_on=today,
                keyword=term,
                item_types=list(features.item_types),
                holders={k: list(v) for k, v in features.holders.items()},
            )
        )
        pulled += 1

    db.commit()
    return pulled, failures


def load(
    db: Session, client: Client, *, today: date | None = None
) -> dict[str, SerpRow]:
    """The newest usable SERP reading per term, keyed lowercase.

    A reading older than `STALE_AFTER_DAYS` is left out rather than used: a
    SERP from two months ago is not evidence about this one, and an action
    argued from it would cite a page that has changed.
    """
    today = today or date.today()
    cutoff = today - timedelta(days=STALE_AFTER_DAYS)

    rows = (
        db.query(FactSerpFeature)
        .filter(
            FactSerpFeature.client_id == client.id,
            FactSerpFeature.pulled_on >= cutoff,
            FactSerpFeature.pulled_on <= today,
        )
        .order_by(FactSerpFeature.pulled_on.desc())
        .all()
    )
    out: dict[str, SerpRow] = {}
    for row in rows:
        key = (row.keyword or "").strip().lower()
        if not key or key in out:
            continue
        out[key] = SerpRow(
            keyword=row.keyword,
            pulled_on=row.pulled_on,
            item_types=frozenset(row.item_types or ()),
            holders={
                k: tuple(v) for k, v in (row.holders or {}).items() if isinstance(v, list)
            },
        )
    return out


def coverage(db: Session, client: Client, *, today: date | None = None) -> tuple[int, int]:
    """How many of the terms worth pulling have a usable reading."""
    wanted = {t.lower() for t in terms_to_pull(db, client)}
    have = set(load(db, client, today=today))
    return len(wanted & have), len(wanted)


# ── Running it ──────────────────────────────────────────────────────────────

SERP_CHECKPOINT = "serp_feature_pull"


def _worth_pulling_for(db: Session, client: Client) -> bool:
    """Whether a SERP reading for this client could be acted on.

    T-2 needs the page's average position and its top query, both of which
    come from Search Console. Without that pull there is nothing to attach a
    SERP feature to, so buying one spends a credit on a reading that expires
    — they are good for 45 days — before anything can read it.
    """
    from app.models.gsc import FactGscPage

    return (
        db.query(FactGscPage.id).filter(FactGscPage.client_id == client.id).first()
        is not None
    )


def maybe_pull_serp_features(db: Session) -> bool:
    """Pull each eligible client's terms, once a month.

    Monthly rather than daily: every query is billed, and a reading is read
    back for 45 days. Returns True when a run was attempted.
    """
    from datetime import datetime, timezone

    from sqlalchemy.exc import IntegrityError

    from app.core.settings import get_settings
    from app.models.scheduler import SchedulerCheckpoint

    settings = get_settings()
    if not settings.serp_pull_enabled or not dataforseo.configured():
        return False

    now = datetime.now(timezone.utc)
    if now.hour < settings.serp_pull_hour_utc:
        return False

    checkpoint = (
        db.query(SchedulerCheckpoint)
        .filter(SchedulerCheckpoint.name == SERP_CHECKPOINT)
        .with_for_update()
        .one_or_none()
    )
    if checkpoint is None:
        checkpoint = SchedulerCheckpoint(name=SERP_CHECKPOINT, last_run_date=None)
        db.add(checkpoint)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return False

    today = now.date()
    last = checkpoint.last_run_date
    # Monthly, not every 30 days: a calendar month is what the spec's cadence
    # means and what somebody reading the bill expects.
    if last is not None and (last.year, last.month) == (today.year, today.month):
        db.rollback()
        return False

    # Claim the month before spending anything. A crash halfway through would
    # otherwise let the next loop start the whole bill again.
    checkpoint.last_run_date = today
    checkpoint.updated_at = now
    db.commit()

    pulled = 0
    skipped = 0
    for client in db.query(Client).all():
        if not _worth_pulling_for(db, client):
            skipped += 1
            continue
        try:
            count, failures = pull(db, client, limit=settings.serp_pull_limit)
        except dataforseo.DataForSeoAuthError:
            # Will not come right for the next client either.
            logger.exception("SERP pull stopped: credentials rejected")
            return True
        pulled += count
        if failures:
            logger.warning(
                "SERP pull for %s: %d failed, first: %s",
                client.slug, len(failures), failures[0],
            )

    logger.info(
        "SERP feature pull: %d query(s) pulled, %d client(s) skipped for want of "
        "Search Console data",
        pulled,
        skipped,
    )
    return True
