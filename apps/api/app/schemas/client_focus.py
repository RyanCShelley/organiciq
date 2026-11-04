from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ClientFocusOut(BaseModel):
    month: str  # YYYY-MM
    focus: Literal["visibility", "traffic", "leads"]
    bucket_id: UUID | None
    bucket_name: str | None


class ClientFocusSet(BaseModel):
    focus: Literal["visibility", "traffic", "leads"]
    bucket_id: UUID | None = None
