from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from app.core.urls import public_host_or_error

Family = Literal["priority_page", "ai_answers", "internal_links", "conversion_path", "structured_data", "investigation"]
Focus = Literal["", "visibility", "traffic", "leads", "continue_strategy", "insufficient_evidence"]


class Brief(BaseModel):
    action_uid: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    id: str = Field(default="MANUAL", max_length=32)
    family: Family
    title: str = Field(min_length=1, max_length=300)
    branch: Literal["visibility", "traffic", "leads"]
    target_url: str = Field(min_length=1, max_length=2048)
    term: str | None = Field(default=None, max_length=1000)
    why: str = Field(min_length=1, max_length=5000)
    done_when: str = Field(min_length=1, max_length=5000)
    steps: list[str] = Field(min_length=1, max_length=30)
    evidence: list[str] = Field(default_factory=list, max_length=100)
    finding_ids: list[str] = Field(default_factory=list, max_length=30)
    effort_min: int = Field(default=60, ge=5, le=180)
    metric: str = Field(min_length=1, max_length=500)
    metric_key: Literal["decision", "term_position", "page_clicks", "page_impressions", "page_position", "engagement_rate", "page_lead_rate", "ai_presence"] = "decision"
    check_after_days: int = Field(default=28, ge=7, le=180)
    check_on: date | None = None
    score: float = 0
    flags: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("target_url")
    @classmethod
    def valid_url(cls, value):
        from urllib.parse import urlsplit
        parts = urlsplit(value)
        if parts.scheme not in ("https", "http"):
            raise ValueError("Use an absolute HTTP or HTTPS target URL.")
        error = public_host_or_error(value)
        if error:
            raise ValueError(error)
        return value.strip()

    @field_validator("steps", "evidence")
    @classmethod
    def lines(cls, values):
        if any(not v.strip() or len(v) > 5000 for v in values):
            raise ValueError("Use nonempty lines of at most 5000 characters.")
        return values


class PlanReviewUpdate(BaseModel):
    revision: int = Field(ge=0)
    strategy: str = Field(default="", max_length=10000)
    focus: Focus = ""
    reason: str = Field(default="", max_length=5000)
    items: list[Brief] = Field(default_factory=list, max_length=100)


class PlanApproval(BaseModel):
    revision: int = Field(ge=0)


class MeasurementSettings(BaseModel):
    target_lead_rate_pct: float | None = Field(default=None, gt=0, le=100)
