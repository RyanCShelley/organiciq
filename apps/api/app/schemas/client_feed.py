from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ClientFeedOut(BaseModel):
    id: UUID
    url: str
    label: str | None


class ClientFeedCreate(BaseModel):
    url: str
    label: str | None = None
