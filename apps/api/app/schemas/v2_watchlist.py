from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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


class WatchlistKeywordAddRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=400)
    bucket_id: UUID | None = None
    bucket_name: str | None = Field(default=None, max_length=160)
    notes: str | None = None

    @field_validator("keyword")
    @classmethod
    def _clean_keyword(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Keyword cannot be blank.")
        return cleaned

    @field_validator("bucket_name")
    @classmethod
    def _clean_bucket_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None

    @field_validator("notes")
    @classmethod
    def _clean_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class WatchlistKeywordAddResponse(BaseModel):
    id: UUID
    keyword: str
    keyword_key: str
    bucket_id: UUID
    bucket_name: str
    created: bool
    bucket_created: bool
