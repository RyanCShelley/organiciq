"""What is held about a search beyond its words: the keyword database's intent label and what its results page shows.

The intent label is DataForSEO's, kept in `facts_ser_keyword_metrics`. Watchlist keywords are priced there by the
monthly job; a growth action can be about any search, so a search with no row is looked up when it is needed and
the answer kept, found or not, so it is paid for once.

The results page comes from `facts_serp_features`, which is only pulled for tracked keywords. A search with no row
there has no results-page signal, and its intent is then provisional.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.integrations import dataforseo
from app.models.client import Client
from app.models.seranking import FactSerKeywordMetric, FactSerpFeature
from app.models.watchlist import WatchlistKeyword

#: A results page older than this is pulled again when an action is built on it.
SERP_FRESH_DAYS = 30

logger = logging.getLogger("organiciq.search_signals")


def _stored_intents(db: Session, client: Client, keyword: str) -> tuple[bool, list[str] | None]:
    row = (
        db.query(FactSerKeywordMetric.intents)
        .filter(FactSerKeywordMetric.client_id == client.id, func.lower(FactSerKeywordMetric.keyword) == keyword)
        .order_by(FactSerKeywordMetric.fetched_at.desc())
        .first()
    )
    return (row is not None, list(row[0]) if row and row[0] else None)


def _pull_intents(db: Session, client: Client, keyword: str, overview=None) -> list[str] | None:
    from app.ingestion.seranking.pipeline_domain import resolve_source

    overview = overview or dataforseo.keyword_overview
    source = resolve_source(client)
    rows = overview([keyword], source=source)
    if not rows:
        return None
    row = rows[0]
    intents = row.get("intents") if isinstance(row.get("intents"), list) else None
    stmt = insert(FactSerKeywordMetric).values(
        id=uuid4(), client_id=client.id, keyword=keyword, source=source, volume=row.get("volume"), difficulty=row.get("difficulty"),
        cpc=row.get("cpc"), competition=row.get("competition"), intents=intents, data_found=bool(row.get("is_data_found", True)), fetched_at=date.today(),
    )
    db.execute(stmt.on_conflict_do_update(constraint="uq_ser_keyword_metrics_grain", set_={"intents": stmt.excluded.intents, "data_found": stmt.excluded.data_found, "fetched_at": stmt.excluded.fetched_at}))
    db.commit()
    return intents


def _watchlist_intents(db: Session, client: Client, keyword: str) -> list[str] | None:
    """The intent recorded on the watchlist keyword, which can be a list ("commercial/transactional/informational")."""
    row = db.query(WatchlistKeyword.intent).filter(WatchlistKeyword.client_id == client.id, WatchlistKeyword.keyword_key == keyword).first()
    if not row or not row[0]:
        return None
    return [part.strip().lower() for part in str(row[0]).replace(",", "/").split("/") if part.strip()]


def _pull_serp(db: Session, client: Client, keyword: str, fetch=None) -> FactSerpFeature:
    features = (fetch or dataforseo.fetch)(keyword)
    # One row a day for a search: a pull made earlier today without its ranking results is filled in, not duplicated.
    today = db.query(FactSerpFeature).filter(FactSerpFeature.client_id == client.id, FactSerpFeature.pulled_on == date.today(), FactSerpFeature.keyword == keyword).first()
    if today is not None:
        today.item_types, today.holders, today.results, today.reading = list(features.item_types), {k: list(v) for k, v in features.holders.items()}, list(features.organic), None
        today.questions = list(features.questions)
        db.commit()
        return today
    row = FactSerpFeature(
        client_id=client.id, pulled_on=date.today(), keyword=keyword, item_types=list(features.item_types),
        holders={k: list(v) for k, v in features.holders.items()}, results=list(features.organic), questions=list(features.questions),
    )
    db.add(row)
    db.commit()
    return row


def _labels(db: Session, client: Client, keyword: str, pull: bool, overview) -> list[str]:
    """Keyword-tool labels for the search. Shown beside the reading; they never decide it."""
    held, intents = _stored_intents(db, client, keyword)
    if not held and pull and dataforseo.configured():
        try:
            intents = _pull_intents(db, client, keyword, overview)
        except Exception:  # A failed lookup costs a reference label, nothing more.
            db.rollback()
            logger.exception("intent label lookup failed for %r", keyword)
    return list(dict.fromkeys([*(intents or []), *(_watchlist_intents(db, client, keyword) or [])]))


def for_search(
    db: Session, client: Client, search: str, *, pull: bool = True, overview=None, fetch=None, ask=None,
) -> dict[str, Any]:
    """`{reading, labels, questions}` for one search: the intent as read from its results page, the tools' labels for
    reference, and the "People also ask" questions the page showed.

    With `pull`, a results page that is missing, over a month old, or was kept without its ranking results is pulled
    again, and a page not yet read is read. So is one that showed a "People also ask" box before its questions were
    kept. Without `pull`, only what is already held is returned: listing pages must not spend anything.
    """
    from app.decisions import serp_intent
    from app.ingestion.seranking.pipeline_domain import resolve_source

    keyword = " ".join((search or "").lower().split())
    if not keyword:
        return {"reading": serp_intent.not_read("There is no search to read."), "labels": []}
    labels = _labels(db, client, keyword, pull, overview)
    serp = (
        db.query(FactSerpFeature)
        .filter(FactSerpFeature.client_id == client.id, func.lower(FactSerpFeature.keyword) == keyword)
        .order_by(FactSerpFeature.pulled_on.desc())
        .first()
    )
    stale = (
        serp is None or not serp.results or (date.today() - serp.pulled_on).days > SERP_FRESH_DAYS
        or (serp.questions is None and "people_also_ask" in (serp.item_types or []))
    )
    pull_error: str | None = None
    if pull and stale:
        if not dataforseo.configured():
            pull_error = "DataForSEO is not configured on this install, so the results page could not be pulled."
        else:
            try:
                serp = _pull_serp(db, client, keyword, fetch)
            except Exception as exc:
                db.rollback()
                logger.exception("results page pull failed for %r", keyword)
                pull_error = f"The results page could not be pulled ({type(exc).__name__})."
    if serp is None or not serp.results:
        reading = serp_intent.not_read(pull_error or ("No results page is held for this search." if serp is None else "The results page held for this search has no ranking results kept."))
        return {"reading": {**reading, "labels": labels, "search": keyword}, "labels": labels}
    # A reading kept before ranked results were listed in it is read again from the same pull: no new results page is bought.
    if serp.reading and serp.reading.get("read") is not None and (serp.reading.get("ranked") is not None or not pull):
        return {"reading": {**serp.reading, "labels": labels, "search": keyword}, "labels": labels, "questions": list(serp.questions or [])}
    if not pull:
        return {"reading": {**serp_intent.not_read("A results page is held for this search but has not been read yet. It is read when an action is built."), "labels": labels, "search": keyword}, "labels": labels}
    reading = serp_intent.read(
        keyword, item_types=list(serp.item_types or []), results=list(serp.results), serp_date=serp.pulled_on.isoformat(),
        labels=labels, market=resolve_source(client), ask=ask,
    )
    # Kept unless the model simply did not answer: a failure should be tried again, a real reading should not be paid for twice.
    reading["search"] = keyword
    if not (reading.get("uncertainty") or "").startswith("The results page could not be read"):
        serp.reading = reading
        db.commit()
    return {"reading": reading, "labels": labels, "questions": list(serp.questions or [])}


def serp_detail(
    db: Session,
    client: Client,
    search: str,
    *,
    pull: bool = False,
    overview=None,
    fetch=None,
    ask=None,
) -> dict[str, Any]:
    """Inspect or pull full stored DataForSEO SERP results, item_types, holders, questions, and reading."""
    keyword = " ".join((search or "").lower().split())
    signals = for_search(db, client, keyword, pull=pull, overview=overview, fetch=fetch, ask=ask)
    serp = (
        db.query(FactSerpFeature)
        .filter(FactSerpFeature.client_id == client.id, func.lower(FactSerpFeature.keyword) == keyword)
        .order_by(FactSerpFeature.pulled_on.desc())
        .first()
    ) if keyword else None
    return {
        "search": keyword,
        "pulled_on": serp.pulled_on.isoformat() if serp else None,
        "item_types": list(serp.item_types or []) if serp else [],
        "features": list(serp.item_types or []) if serp else [],
        "holders": serp.holders or {} if serp else {},
        "results": list(serp.results or []) if serp else [],
        "questions": list(serp.questions or []) if serp else [],
        "reading": signals["reading"],
        "labels": signals.get("labels") or [],
        "configured": dataforseo.configured(),
    }
