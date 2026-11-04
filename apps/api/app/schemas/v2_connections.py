from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BingSiteOut(BaseModel):
    site_url: str
    status: str
    error: str | None
    checked_at: datetime | None


class BingSiteSet(BaseModel):
    site_url: str


class ConnectionsOut(BaseModel):
    teamwork_configured: bool
    teamwork_tasklist_id: str | None
    teamwork_content_tasklist_id: str | None
    bing_key_configured: bool
    bing: BingSiteOut | None
    se_ranking_key_configured: bool
    google_connect_configured: bool


class BingSiteChoice(BaseModel):
    url: str
    verified: bool
