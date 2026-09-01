from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.settings import get_settings
from app.models.user import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthUser:
    id: UUID
    email: str
    name: str | None
    role: UserRole
    google_sub: str | None
    is_active: bool


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.auth_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    payload = decode_token(credentials.credentials)
    email = (payload.get("email") or "").lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing email",
        )

    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None:
        settings = get_settings()
        hosted = settings.sma_google_hosted_domain.lower()
        if not email.endswith(f"@{hosted}"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        # Early product phases: any SMA Workspace login is treated as admin.
        # Tighten to SMA_ADMIN_EMAILS / team assignments before client portal.
        user = User(
            email=email,
            name=payload.get("name"),
            google_sub=payload.get("sub"),
            role=UserRole.SMA_ADMIN,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return AuthUser(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        google_sub=user.google_sub,
        is_active=user.is_active,
    )


def require_sma_staff(user: Annotated[AuthUser, Depends(get_current_user)]) -> AuthUser:
    if user.role not in {UserRole.SMA_ADMIN, UserRole.SMA_TEAM}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SMA staff access required",
        )
    return user


def require_sma_admin(user: Annotated[AuthUser, Depends(get_current_user)]) -> AuthUser:
    if user.role != UserRole.SMA_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SMA admin access required",
        )
    return user
