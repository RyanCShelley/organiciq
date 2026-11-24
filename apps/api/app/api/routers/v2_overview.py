from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.schemas.v2_overview import ClientsOverviewOut
from app.services.clients_overview import build_clients_overview

router = APIRouter(prefix="/v2/clients", tags=["v2 overview"])


@router.get("/overview", response_model=ClientsOverviewOut)
def get_clients_overview(
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    as_of: date | None = Query(default=None, ge=date(2000, 1, 1)),
) -> ClientsOverviewOut:
    return build_clients_overview(db, user, as_of=as_of)
