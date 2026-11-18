"""Text vectors for body paragraphs, worked out once and kept.

A paragraph is embedded with the same pinned MiniLM model the keyword matcher uses, which reads about 200 words at
a time: a paragraph fits it, a whole page does not. The vector is stored against a hash of the paragraph's text,
so a crawl that replaces every page row does not cost a second embedding of text that did not change.

Search over these is exact (a dot product over every candidate). At the crawl's ceiling of 5,000 pages that is
well under a second, and an approximate index would only trade accuracy for speed nobody is short of.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.crawl import PageParagraphVector

logger = logging.getLogger("organiciq.paragraph_vectors")

DIMENSIONS = 384
_BATCH = 500


def text_hash(text: str) -> str:
    return hashlib.sha1(" ".join((text or "").split()).lower().encode("utf-8")).hexdigest()


def ensure(db: Session, client_id: Any, texts: list[str], embed=None) -> dict[str, Any]:
    """`{text_hash: vector}` for every text given: read from the store, and the missing ones embedded and saved."""
    import numpy as np

    wanted = {text_hash(t): t for t in texts if (t or "").strip()}
    if not wanted:
        return {}
    held: dict[str, Any] = {}
    keys = list(wanted)
    for i in range(0, len(keys), 2000):
        for h, raw in db.query(PageParagraphVector.text_hash, PageParagraphVector.vector).filter(
            PageParagraphVector.client_id == client_id, PageParagraphVector.text_hash.in_(keys[i : i + 2000])
        ):
            vector = np.frombuffer(raw, dtype="float32")
            if vector.shape[0] == DIMENSIONS:
                held[h] = vector
    missing = [h for h in keys if h not in held]
    if missing:
        if embed is None:
            from app.services.keyword_matcher import _embed as embed
        for i in range(0, len(missing), _BATCH):
            batch = missing[i : i + _BATCH]
            matrix = embed([wanted[h] for h in batch])
            rows = [{"id": uuid4(), "client_id": client_id, "text_hash": h, "vector": np.asarray(matrix[n], dtype="float32").tobytes()} for n, h in enumerate(batch)]
            db.execute(insert(PageParagraphVector).values(rows).on_conflict_do_nothing(constraint="uq_page_paragraph_vectors_grain"))
            held.update({h: np.asarray(matrix[n], dtype="float32") for n, h in enumerate(batch)})
        db.commit()
        logger.info("embedded %d new paragraphs for client %s", len(missing), client_id)
    return held


def prune(db: Session, client_id: Any, keep: set[str]) -> int:
    """Remove the vectors no current paragraph uses. Called after a crawl has replaced the pages."""
    held = [h for (h,) in db.query(PageParagraphVector.text_hash).filter(PageParagraphVector.client_id == client_id)]
    gone = [h for h in held if h not in keep]
    for i in range(0, len(gone), 2000):
        db.query(PageParagraphVector).filter(PageParagraphVector.client_id == client_id, PageParagraphVector.text_hash.in_(gone[i : i + 2000])).delete(synchronize_session=False)
    return len(gone)
