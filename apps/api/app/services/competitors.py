"""The competitors a client's team names, which the gap analysis reads.

Chosen in client settings, not taken from whatever SE Ranking happens to track:
the people running the account know who they actually compete with, and each
one read costs 100 credits.
"""

from __future__ import annotations

from urllib.parse import urlsplit

#: Each competitor read is one 100-credit request a month.
MAX_COMPETITORS = 3


def bare_domain(value: str | None) -> str:
    """`https://www.Example.com/path` → `example.com`."""
    text = (value or "").strip().lower()
    if "://" in text:
        text = urlsplit(text).netloc or text
    return text.split("/")[0].removeprefix("www.")


def clean_competitor_domains(values: list[str] | None, *, own_domain: str | None = None) -> list[str]:
    """Bare, deduplicated domains. Raises if more than `MAX_COMPETITORS` are named.

    Anything without a dot is dropped (a typo or a company name is not a domain
    SE Ranking can read), as is the client's own domain.
    """
    own = bare_domain(own_domain)
    seen: dict[str, None] = {}
    for value in values or []:
        domain = bare_domain(str(value))
        if "." in domain and " " not in domain and domain != own:
            seen[domain] = None
    if len(seen) > MAX_COMPETITORS:
        raise ValueError(f"name at most {MAX_COMPETITORS} competitors, not {len(seen)}")
    return list(seen)
