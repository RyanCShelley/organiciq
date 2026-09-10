"""Shared retry/backoff for Google API calls.

The GSC and GA4 clients previously called `raise_for_status()` directly, so a
single 429 or transient 5xx failed the whole sync job. Google returns both
routinely once several clients sync in the same window — and at 35 clients the
daily cycle is exactly that.

SE Ranking's client already did this; this is the Google-side equivalent.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable

import httpx

logger = logging.getLogger("organiciq.google_http")

RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4
BASE_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Honour Retry-After when Google sends it (seconds form only)."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw.strip()))
    except ValueError:
        return None


def _backoff_seconds(attempt: int, response: httpx.Response | None) -> float:
    if response is not None:
        explicit = _retry_after_seconds(response)
        if explicit is not None:
            return min(explicit, MAX_BACKOFF_SECONDS)
    # Exponential with jitter, so parallel workers do not retry in lockstep.
    window = min(BASE_BACKOFF_SECONDS * (2**attempt), MAX_BACKOFF_SECONDS)
    return window / 2 + random.random() * (window / 2)


def request_with_retry(
    send: Callable[[], httpx.Response],
    *,
    description: str,
    max_attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """
    Call `send`, retrying throttling and transient server errors.

    4xx other than 408/429 are permanent (bad property, revoked scope) and are
    raised immediately — retrying them just burns quota.
    """
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        response: httpx.Response | None = None
        try:
            response = send()
            if response.status_code not in RETRY_STATUS:
                response.raise_for_status()
                return response
            last_error = httpx.HTTPStatusError(
                f"{description} failed with {response.status_code}",
                request=response.request,
                response=response,
            )
        except httpx.HTTPStatusError:
            raise
        except httpx.RequestError as exc:
            # Connection reset / timeout — worth another attempt.
            last_error = exc

        if attempt + 1 >= max_attempts:
            break

        delay = _backoff_seconds(attempt, response)
        logger.warning(
            "%s: retrying in %.1fs (attempt %d/%d, status=%s)",
            description,
            delay,
            attempt + 1,
            max_attempts,
            response.status_code if response is not None else "connection error",
        )
        sleep(delay)

    assert last_error is not None
    raise last_error


def post_json(
    client: httpx.Client, url: str, *, headers: dict[str, str], json: Any, description: str
) -> httpx.Response:
    return request_with_retry(
        lambda: client.post(url, headers=headers, json=json), description=description
    )


def get(
    client: httpx.Client, url: str, *, headers: dict[str, str], description: str
) -> httpx.Response:
    return request_with_retry(lambda: client.get(url, headers=headers), description=description)
