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
        # An SMA Workspace login is provisioned at the lowest useful role.
        # Admin comes only from SMA_ADMIN_EMAILS — never from the domain alone,
        # or every staff address would silently hold full cross-client access.
        user = User(
            email=email,
            name=payload.get("name"),
            google_sub=payload.get("sub"),
            role=(
                UserRole.SMA_ADMIN
                if email in settings.admin_email_set
                else UserRole.SMA_TEAM
            ),
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
