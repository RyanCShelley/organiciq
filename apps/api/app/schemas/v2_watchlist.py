from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class WatchlistKeywordOut(BaseModel):
    id: UUID
    keyword: str
    volume: int | None
    difficulty: int | None
    intent: str | None
    paired_ai_prompt: str | None
    notes: str | None


class WatchlistBucketOut(BaseModel):
    id: UUID
    name: str
    sort_order: int
    keywords: list[WatchlistKeywordOut]


class WatchlistOut(BaseModel):
    buckets: list[WatchlistBucketOut]
    keyword_count: int


class WatchlistImportRequest(BaseModel):
    csv_text: str
    #: Report what would change without writing anything.
    dry_run: bool = False


class WatchlistImportResponse(BaseModel):
    dry_run: bool
    rows_read: int
    buckets_created: int
    keywords_created: int
    keywords_updated: int
    keywords_unchanged: int
    #: Rows whose topic came from the row above (merged cells in the sheet).
    topics_inherited: int
    skipped: list[dict]
    warnings: list[dict]
    ignored_columns: list[str]
