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


def rewrite_url_host(raw_url: str, target_host: str) -> str:
    """Replace the URL host with target_host, preserving path/query/fragment."""
    host = (target_host or "").strip()
    if not host:
        return raw_url
    if "://" in host:
        host = urlsplit(host).hostname or host
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return raw_url

    value = (raw_url or "").strip()
    if not value:
        return raw_url
    if "://" not in value:
        value = f"https://{value}"

    parts = urlsplit(value)
    scheme = (parts.scheme or "https").lower()
    if scheme not in {"http", "https"}:
        scheme = "https"
    return urlunsplit((scheme, host, parts.path or "/", parts.query, parts.fragment))


def normalize_landing_page(raw: str, domain: str | None = None) -> str:
    """Canonical landing page. GA4 often returns a path; prefix with client domain when present."""
    value = (raw or "").strip()
    if value.lower() in _LANDING_SENTINELS:
        return value.lower()
    if value.startswith("/"):
        host = _host_only(domain)
        if host:
            return normalize_url(f"https://{host}{value}")
        path = value.lower()
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return path
    return normalize_url(value)


def _host_only(value: str | None) -> str:
    """The bare host from anything domain-shaped.

    A client's path scope lives in its own field, but a path has been typed into
    the domain before now — and silently joining it onto a GA4 path produced
    `/section/section/page`, which still looks like a URL. Taking only the host
    makes that impossible.
    """
    host = (value or "").strip().lower()
    if not host:
        return ""
    if "://" in host:
        host = urlsplit(host).hostname or ""
    else:
        host = host.split("/", 1)[0]
    return host.removeprefix("www.").strip().strip(".")


def normalize_path_prefix(value: str | None) -> str | None:
    """Canonical path scope, or None for a whole site.

    Accepts the shapes a person types: `unmanned`, `/unmanned/`, or a full URL.
    Returns a lowercase path with a leading slash and no trailing one, matching
    how `normalize_url` stores paths so the two can be compared directly.
    """
    text = (value or "").strip()
    if not text:
        return None
    if "://" in text:
        text = urlsplit(text).path
    text = text.split("?", 1)[0].split("#", 1)[0]
    text = "/" + text.strip("/").lower()
    return None if text == "/" else text


def url_in_scope(normalized_url: str, prefix: str | None) -> bool:
    """Whether a URL belongs to a client scoped to `prefix`.

    A prefix matches its own page and anything beneath it, but not a sibling
    that merely starts with the same letters: `/unmanned` must not claim
    `/unmanned-sales`. Comparing on a path boundary is what makes that hold.
    """
    if not prefix:
        return True
    if not normalized_url:
        return False
    path = urlsplit(normalized_url).path.lower().rstrip("/") or "/"
    return path == prefix or path.startswith(f"{prefix}/")
