"""The web app's auth middleware cannot be absent from a commit.

Verifying a server-rendered page locally means getting past the sign-in
redirect, and the quickest way is to move `middleware.ts` aside. That is
fine until a `git add -A` sweeps the renamed file into a commit, which is
exactly what happened on 8 October 2026: one production deploy went out
with the file named `middleware.ts.PARKED` and served every page without
a session check for about three minutes.

Nothing was exposed — the API rejects a request with no bearer token, so
the pages rendered and then failed to load anything — but the next
mistake of this shape need not be so lucky. The file is small, the check
is cheap, and a parked file is unambiguous evidence of a session that was
not cleaned up.
"""

from __future__ import annotations

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web"


def test_the_auth_middleware_is_present():
    middleware = WEB / "middleware.ts"
    assert middleware.is_file(), (
        "apps/web/middleware.ts is missing. If it was moved aside to preview a "
        "page locally, move it back before committing."
    )
    source = middleware.read_text(encoding="utf-8")
    assert "auth(" in source and "/login" in source, (
        "apps/web/middleware.ts no longer redirects an unauthenticated request "
        "to /login."
    )


def test_nothing_is_left_parked():
    """A parked file is a local workaround that escaped into the tree."""
    parked = sorted(
        str(path.relative_to(WEB.parent))
        for path in WEB.rglob("*.PARKED")
        if "node_modules" not in path.parts and ".next" not in path.parts
    )
    assert parked == [], "parked files committed: " + ", ".join(parked)
