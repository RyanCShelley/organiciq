import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.core.settings import get_settings
from app.schemas import AuthUpsertRequest, HealthOut, UserOut
from app.services import auth as auth_service

router = APIRouter(tags=["auth"])


def require_internal_caller(
    x_organiciq_internal_secret: Annotated[str | None, Header(alias="X-OrganicIQ-Internal-Secret")] = None,
) -> None:
    """
    Guard the sign-in upsert, which mints staff users.

    Only the web app may call it. Outside production an unset secret keeps
    local development working; settings refuses to boot without one in
    production.
    """
    settings = get_settings()
    expected = settings.internal_api_secret
    if not expected:
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Internal API secret not configured",
            )
        return
    if not x_organiciq_internal_secret or not hmac.compare_digest(
        x_organiciq_internal_secret, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal credentials",
        )


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok", service="organiciq-api")


@router.post("/auth/upsert", response_model=UserOut)
def upsert_user(
    payload: AuthUpsertRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_internal_caller)] = None,
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
