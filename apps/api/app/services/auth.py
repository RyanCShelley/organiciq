
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.user import User, UserRole
from app.schemas import AuthUpsertRequest


def _free_google_sub(db: Session, google_sub: str | None, *, owner: User | None) -> str | None:
    """The Google id to store, or None when another row already holds it.

    One Google account can sign in under more than one address — an alias, or
    the same person on `.com` and `.net` — and Google reports the same id for
    all of them. The column is unique, so handing it to a second row is a
    duplicate-key error, which the sign-in (now failing closed) turned into
    "AccessDenied" for the second address. The id identifies a person, not an
    email, so the first row to claim it keeps it and the others are left
    without one; they are matched by email, which is what everything reads.
    """
    if not google_sub:
        return None
    query = db.query(User.id).filter(User.google_sub == google_sub)
    if owner is not None:
        query = query.filter(User.id != owner.id)
    return None if query.first() is not None else google_sub


def upsert_user(db: Session, payload: AuthUpsertRequest) -> User:
    settings = get_settings()
    email = payload.email.lower()
    user = db.query(User).filter(User.email == email).one_or_none()

    if user is None:
        role = UserRole.SMA_ADMIN if email in settings.admin_email_set else UserRole.SMA_TEAM
        user = User(
            email=email,
            name=payload.name,
            google_sub=_free_google_sub(db, payload.google_sub, owner=None),
            role=role,
            is_active=True,
        )
        db.add(user)
    else:
        user.name = payload.name or user.name
        # Keep what is stored unless the incoming id is free to take.
        user.google_sub = _free_google_sub(db, payload.google_sub, owner=user) or user.google_sub
        if email in settings.admin_email_set:
            user.role = UserRole.SMA_ADMIN

    db.commit()
    db.refresh(user)
    return user


