from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.review_visibility import key_of

INT4_MAX = 2_147_483_647
KEYWORD_MAX_LENGTH = 400
BUCKET_NAME_MAX_LENGTH = 160


def _reject_nul(value: str, label: str = "Value") -> None:
    if "\x00" in value:
        raise ValueError(f"{label} cannot contain NUL characters.")


def _clean_collapsed(value: str, label: str, *, max_key_length: int | None = None) -> str:
    _reject_nul(value, label)
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError(f"{label} cannot be blank.")
    if max_key_length is not None and len(key_of(cleaned)) > max_key_length:
        raise ValueError(f"{label} must be at most {max_key_length} characters after normalization.")
    return cleaned


def _clean_optional_collapsed(value: str | None) -> str | None:
    if value is None:
        return None
    _reject_nul(value)
    cleaned = " ".join(value.split())
    return cleaned or None


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    _reject_nul(value)
    cleaned = value.strip()
    return cleaned or None


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
    keyword: str = Field(min_length=1, max_length=KEYWORD_MAX_LENGTH)
    bucket_id: UUID | None = None
    bucket_name: str | None = Field(default=None, max_length=BUCKET_NAME_MAX_LENGTH)
    volume: int | None = Field(default=None, ge=0, le=INT4_MAX)
    difficulty: int | None = Field(default=None, ge=0, le=100)
    intent: str | None = Field(default=None, max_length=120)
    paired_ai_prompt: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("keyword")
    @classmethod
    def _clean_keyword(cls, value: str) -> str:
        return _clean_collapsed(value, "Keyword", max_key_length=KEYWORD_MAX_LENGTH)

    @field_validator("bucket_name")
    @classmethod
    def _clean_bucket_name(cls, value: str | None) -> str | None:
        cleaned = _clean_optional_collapsed(value)
        if cleaned is not None and len(key_of(cleaned)) > BUCKET_NAME_MAX_LENGTH:
            raise ValueError(
                f"Bucket name must be at most {BUCKET_NAME_MAX_LENGTH} characters after normalization."
            )
        return cleaned

    @field_validator("intent")
    @classmethod
    def _clean_intent(cls, value: str | None) -> str | None:
        return _clean_optional_collapsed(value)

    @field_validator("paired_ai_prompt", "notes")
    @classmethod
    def _clean_optional_multiline(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class WatchlistKeywordAddResponse(BaseModel):
    id: UUID
    keyword: str
    keyword_key: str
    bucket_id: UUID
    bucket_name: str
    created: bool
    bucket_created: bool


class WatchlistKeywordUpdateRequest(BaseModel):
    keyword: str | None = Field(default=None, max_length=KEYWORD_MAX_LENGTH)
    bucket_id: UUID | None = None
    bucket_name: str | None = Field(default=None, max_length=BUCKET_NAME_MAX_LENGTH)
    volume: int | None = Field(default=None, ge=0, le=INT4_MAX)
    difficulty: int | None = Field(default=None, ge=0, le=100)
    intent: str | None = Field(default=None, max_length=120)
    paired_ai_prompt: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("keyword")
    @classmethod
    def _clean_keyword(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_collapsed(value, "Keyword", max_key_length=KEYWORD_MAX_LENGTH)

    @field_validator("bucket_name")
    @classmethod
    def _clean_bucket_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_collapsed(value, "Bucket name", max_key_length=BUCKET_NAME_MAX_LENGTH)

    @field_validator("intent")
    @classmethod
    def _clean_intent(cls, value: str | None) -> str | None:
        return _clean_optional_collapsed(value)

    @field_validator("paired_ai_prompt", "notes")
    @classmethod
    def _clean_optional_multiline(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)

    @model_validator(mode="after")
    def _validate_fields(self) -> WatchlistKeywordUpdateRequest:
        fields = self.model_fields_set
        if "keyword" in fields and self.keyword is None:
            raise ValueError("Keyword cannot be null.")
        if (
            "bucket_name" in fields
            and self.bucket_name is None
            and not ("bucket_id" in fields and self.bucket_id is not None)
        ):
            raise ValueError("bucket_name cannot be null.")
        if (
            "bucket_id" in fields
            and self.bucket_id is None
            and not ("bucket_name" in fields and self.bucket_name is not None)
        ):
            raise ValueError("bucket_id cannot be null unless bucket_name is provided.")
        if (
            "bucket_id" in fields
            and self.bucket_id is not None
            and "bucket_name" in fields
            and self.bucket_name is not None
        ):
            raise ValueError("Provide either bucket_id or bucket_name, not both.")
        return self


class WatchlistKeywordDetailOut(WatchlistKeywordOut):
    bucket_id: UUID
    bucket_name: str
    source: str


class WatchlistKeywordBulkAddRequest(BaseModel):
    items: list[WatchlistKeywordAddRequest] = Field(min_length=1, max_length=100)


class WatchlistKeywordBulkAddResponse(BaseModel):
    results: list[WatchlistKeywordAddResponse]
    created_count: int
    existing_count: int


class WatchlistBucketCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=BUCKET_NAME_MAX_LENGTH)
    sort_order: int | None = Field(default=None, ge=0, le=INT4_MAX)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return _clean_collapsed(value, "Bucket name", max_key_length=BUCKET_NAME_MAX_LENGTH)


class WatchlistBucketUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=BUCKET_NAME_MAX_LENGTH)
    sort_order: int | None = Field(default=None, ge=0, le=INT4_MAX)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_collapsed(value, "Bucket name", max_key_length=BUCKET_NAME_MAX_LENGTH)

    @model_validator(mode="after")
    def _validate_non_null(self) -> WatchlistBucketUpdateRequest:
        fields = self.model_fields_set
        if "name" in fields and self.name is None:
            raise ValueError("Bucket name cannot be null.")
        if "sort_order" in fields and self.sort_order is None:
            raise ValueError("sort_order cannot be null.")
        return self


class WatchlistBucketDeleteResponse(BaseModel):
    deleted: bool
    id: UUID
    deleted_keywords: int
    cleared_focuses: int


class WatchlistSuggestionOut(BaseModel):
    query: str
    key: str
    page: str | None
    impressions: int
    impressions_before: int
    impressions_change_pct: float | None
    clicks: int
    position: float | None
    position_before: float | None
    move: float | None
    ctr: float | None
    signals: list[str]
    relevance_note: str


class WatchlistSuggestionsOut(BaseModel):
    gsc_connected: bool
    has_gsc_data: bool
    google_through: str | None
    days: int
    suggestions: list[WatchlistSuggestionOut]
