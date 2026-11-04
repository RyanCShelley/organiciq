"""Read a client's watchlist from the CSV export of their account sheet.

The sheet is built for people, not for import, so the reader is forgiving about
what people do to sheets:

* The header row need not be the first row.
* Columns are matched by name, in any order. `Current Position` and `Why` are
  recognised and left out on purpose; so is anything unlabelled or unknown, and
  each is reported so a dropped column is never a surprise.
* A topic written once over merged cells exports as one value and blanks. A
  blank topic takes the topic above it, and the report counts how often that
  happened, so a genuinely missing topic does not quietly join the wrong bucket.
* A blank cell never erases what is already stored.

Importing is an upsert by keyword. Nothing is deleted: a keyword missing from
the file stays.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.watchlist import WatchlistBucket, WatchlistKeyword

#: Normalised header -> field.
_ALIASES: dict[str, str] = {
    "topic": "topic",
    "bucket": "topic",
    "watchlist bucket": "topic",
    "topic bucket": "topic",
    "keyword": "keyword",
    "term": "keyword",
    "keyword phrase": "keyword",
    "volume": "volume",
    "search volume": "volume",
    "monthly volume": "volume",
    "difficulty": "difficulty",
    "kd": "difficulty",
    "keyword difficulty": "difficulty",
    "paired ai prompt": "prompt",
    "paired prompt": "prompt",
    "ai prompt": "prompt",
    "prompt": "prompt",
    "intent": "intent",
    "search intent": "intent",
    "notes": "notes",
    "note": "notes",
}

#: Present in the sheet and deliberately not imported.
_LEFT_OUT = {"current position", "position", "why"}

_FIELDS = ("volume", "difficulty", "intent", "prompt", "notes")


def _header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _key(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _number(raw: str) -> int | None:
    cleaned = raw.replace(",", "").replace(" ", "")
    if not cleaned:
        return None
    return int(round(float(cleaned)))


@dataclass
class ParsedRow:
    line: int
    topic: str
    keyword: str
    values: dict[str, Any]
    topic_inherited: bool = False


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    ignored_columns: list[str] = field(default_factory=list)
    #: Which optional columns the file has. A column the file lacks is left alone.
    columns_present: set[str] = field(default_factory=set)


def parse_watchlist_csv(csv_text: str) -> ParseResult:
    rows = list(csv.reader(io.StringIO(csv_text.lstrip("﻿"))))

    header_at = None
    for index, row in enumerate(rows[:10]):
        fields = {_ALIASES.get(_header_key(cell)) for cell in row}
        if "topic" in fields and "keyword" in fields:
            header_at = index
            break
    if header_at is None:
        raise ValueError("Could not find a header row with both a Topic and a Keyword column")

    header = rows[header_at]
    column_of: dict[str, int] = {}
    result = ParseResult()
    for position, cell in enumerate(header):
        name = _header_key(cell)
        target = _ALIASES.get(name)
        if target and target not in column_of:
            column_of[target] = position
        elif name and name not in _LEFT_OUT:
            result.ignored_columns.append(cell.strip())
        elif name in _LEFT_OUT:
            result.ignored_columns.append(cell.strip())
        elif any(len(r) > position and r[position].strip() for r in rows[header_at + 1 :]):
            result.ignored_columns.append(f"(unlabelled column {position + 1})")
    result.columns_present = {f for f in _FIELDS if f in column_of}

    def cell(row: list[str], name: str) -> str:
        position = column_of.get(name)
        return row[position].strip() if position is not None and position < len(row) else ""

    last_topic = ""
    seen: dict[str, int] = {}
    for offset, row in enumerate(rows[header_at + 1 :], start=header_at + 2):
        if not any(c.strip() for c in row):
            continue
        keyword = cell(row, "keyword")
        if not keyword:
            result.skipped.append({"line": offset, "reason": "no keyword"})
            continue

        topic = cell(row, "topic")
        inherited = False
        if not topic:
            if not last_topic:
                result.skipped.append(
                    {"line": offset, "keyword": keyword, "reason": "no topic, and none above to use"}
                )
                continue
            topic, inherited = last_topic, True
        else:
            last_topic = topic

        values: dict[str, Any] = {}
        for name in ("volume", "difficulty"):
            raw = cell(row, name)
            if not raw:
                continue
            try:
                number = _number(raw)
            except ValueError:
                result.warnings.append(
                    {"line": offset, "keyword": keyword, "reason": f"{name} {raw!r} is not a number"}
                )
                continue
            if name == "difficulty" and number is not None and not 0 <= number <= 100:
                result.warnings.append(
                    {"line": offset, "keyword": keyword, "reason": f"difficulty {number} is outside 0 to 100"}
                )
                continue
            values[name] = number
        for name in ("intent", "prompt", "notes"):
            raw = cell(row, name)
            if raw:
                values[name] = raw

        key = _key(keyword)
        if key in seen:
            result.warnings.append(
                {
                    "line": offset,
                    "keyword": keyword,
                    "reason": f"also on line {seen[key]}; the later row is used",
                }
            )
            result.rows = [r for r in result.rows if _key(r.keyword) != key]
        seen[key] = offset
        result.rows.append(ParsedRow(offset, topic, keyword, values, inherited))
    return result


_COLUMN_OF_FIELD = {
    "volume": "volume",
    "difficulty": "difficulty",
    "intent": "intent",
    "prompt": "paired_ai_prompt",
    "notes": "notes",
}


def import_watchlist(
    db: Session, client: Client, csv_text: str, *, dry_run: bool = False, source: str = "csv"
) -> dict[str, Any]:
    parsed = parse_watchlist_csv(csv_text)

    buckets = {
        b.name_key: b
        for b in db.query(WatchlistBucket).filter(WatchlistBucket.client_id == client.id).all()
    }
    keywords = {
        k.keyword_key: k
        for k in db.query(WatchlistKeyword).filter(WatchlistKeyword.client_id == client.id).all()
    }
    next_order = max((b.sort_order for b in buckets.values()), default=-1) + 1

    new_buckets: dict[str, WatchlistBucket] = {}
    created = updated = unchanged = inherited = 0

    for row in parsed.rows:
        inherited += row.topic_inherited
        bucket_key = _key(row.topic)
        bucket = buckets.get(bucket_key) or new_buckets.get(bucket_key)
        if bucket is None:
            bucket = WatchlistBucket(
                client_id=client.id, name=row.topic, name_key=bucket_key, sort_order=next_order
            )
            next_order += 1
            new_buckets[bucket_key] = bucket
            if not dry_run:
                db.add(bucket)
                db.flush()

        existing = keywords.get(_key(row.keyword))
        if existing is None:
            created += 1
            if not dry_run:
                db.add(
                    WatchlistKeyword(
                        client_id=client.id,
                        bucket_id=bucket.id,
                        keyword=row.keyword,
                        keyword_key=_key(row.keyword),
                        source=source,
                        **{_COLUMN_OF_FIELD[k]: v for k, v in row.values.items()},
                    )
                )
            continue

        changed = False
        if not dry_run and existing.bucket_id != bucket.id:
            existing.bucket_id = bucket.id
            changed = True
        elif dry_run and bucket_key != _bucket_key_of(existing, buckets):
            changed = True
        for name, value in row.values.items():
            attribute = _COLUMN_OF_FIELD[name]
            if getattr(existing, attribute) != value:
                changed = True
                if not dry_run:
                    setattr(existing, attribute, value)
        if changed:
            updated += 1
        else:
            unchanged += 1

    if not dry_run:
        db.commit()

    return {
        "dry_run": dry_run,
        "rows_read": len(parsed.rows),
        "buckets_created": len(new_buckets),
        "keywords_created": created,
        "keywords_updated": updated,
        "keywords_unchanged": unchanged,
        "topics_inherited": inherited,
        "skipped": parsed.skipped,
        "warnings": parsed.warnings,
        "ignored_columns": parsed.ignored_columns,
    }


def _bucket_key_of(keyword: WatchlistKeyword, buckets: dict[str, WatchlistBucket]) -> str | None:
    for key, bucket in buckets.items():
        if bucket.id == keyword.bucket_id:
            return key
    return None
