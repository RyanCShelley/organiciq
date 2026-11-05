"""The email a new team member gets when an admin adds them."""
from __future__ import annotations

import logging

from app.core.settings import get_settings
from app.services import health_digest

logger = logging.getLogger("organiciq.welcome")


def render(*, name: str | None, email: str, added_by: str | None, restored: bool) -> tuple[str, str]:
    url = get_settings().web_v2_app_url.rstrip("/") + "/login"
    who = f" by {added_by}" if added_by else ""
    lines = [
        f"Hi {name.split()[0]}," if name else "Hi,",
        "",
        f"You {'have been let back in to' if restored else 'have been added to'} Organic IQ{who}.",
        "",
        "To sign in:",
        f"  1. Go to {url}",
        "  2. Choose \"Continue with Google\".",
        f"  3. Use your work account, {email}.",
        "",
        "There is no separate password: your Google sign-in is the login.",
        "You will see the clients you have been given access to. If one is missing, ask the person who added you.",
    ]
    return "You have access to Organic IQ", "\n".join(lines)


def send(*, name: str | None, email: str, added_by: str | None, restored: bool) -> bool:
    """True when it was sent. Never raises: the person is already added, and a mail failure must not undo that."""
    subject, body = render(name=name, email=email, added_by=added_by, restored=restored)
    try:
        return health_digest.send_email(subject, body, to=[email])
    except Exception:
        logger.exception("Welcome email to %s failed", email)
        return False
