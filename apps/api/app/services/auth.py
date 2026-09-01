from uuid import UUID

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.user import User, UserRole
from app.schemas import AuthUpsertRequest


def upsert_user(db: Session, payload: AuthUpsertRequest) -> User:
    settings = get_settings()
    email = payload.email.lower()
    user = db.query(User).filter(User.email == email).one_or_none()

    if user is None:
        role = UserRole.SMA_ADMIN if email in settings.admin_email_set else UserRole.SMA_TEAM
        user = User(
            email=email,
            name=payload.name,
            google_sub=payload.google_sub,
            role=role,
            is_active=True,
        )
        db.add(user)
    else:
        user.name = payload.name or user.name
        user.google_sub = payload.google_sub
        if email in settings.admin_email_set:
            user.role = UserRole.SMA_ADMIN

    db.commit()
    db.refresh(user)
    return user


def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    return db.query(User).filter(User.id == user_id).one_or_none()
