from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import AuthUser, get_current_user, require_sma_staff
from app.schemas import AuthUpsertRequest, HealthOut, UserOut
from app.services import auth as auth_service

router = APIRouter(tags=["auth"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok", service="organiciq-api")


@router.post("/auth/upsert", response_model=UserOut)
def upsert_user(
    payload: AuthUpsertRequest,
    db: Annotated[Session, Depends(get_db)],
) -> UserOut:
    user = auth_service.upsert_user(db, payload)
    return UserOut.model_validate(user)


@router.get("/auth/me", response_model=UserOut)
def me(user: Annotated[AuthUser, Depends(require_sma_staff)]) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
    )
