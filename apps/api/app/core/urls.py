from urllib.parse import urlsplit, urlunsplit

_LANDING_SENTINELS = {"(not set)", "(not provided)", "(none)", ""}


def normalize_url(raw: str) -> str:
    """Canonical URL for cross-source joins.

    Handles protocol, www, trailing slash, query, fragment, and host case.
    Path case is lowercased; original URL must still be stored separately as raw_url.
    """
    if not raw:
        return ""

    value = raw.strip()
    if not value:
        return ""

    if "://" not in value:
        value = f"https://{value}"

    parts = urlsplit(value)
    scheme = (parts.scheme or "https").lower()
    if scheme not in {"http", "https"}:
        scheme = "https"

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    netloc = host
    if parts.port and parts.port not in {80, 443}:
        netloc = f"{host}:{parts.port}"

    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    path = path.lower()

    # Drop query and fragment for canonical page identity.
    return urlunsplit((scheme, netloc, path, "", ""))


def normalize_landing_page(raw: str, domain: str | None = None) -> str:
    """Canonical landing page. GA4 often returns a path; prefix with client domain when present."""
    value = (raw or "").strip()
    if value.lower() in _LANDING_SENTINELS:
        return value.lower()
    if value.startswith("/"):
        host = (domain or "").strip()
        if host:
            if "://" in host:
                host = urlsplit(host).hostname or host
            return normalize_url(f"https://{host}{value}")
        path = value.lower()
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return path
    return normalize_url(value)
