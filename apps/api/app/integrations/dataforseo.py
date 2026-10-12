"""The full SERP feature list for a query.

`facts_ser_keywords.earned_serp_features` holds the features a client already
*holds* — which answers "what did we win" and not "what is on this page". V-5
and T-2 both need the second question: T-2 fires on a feature present that the
client does not hold, and V-5 on a query showing an AI Overview or a snippet
that the page gives nothing extractable to fill. Neither could ever fire, and
both have sat in BLOCKED_ACTIONS saying so.

DataForSEO's live endpoint answers it directly: `result.item_types` is every
element type on the SERP, held or not, which is the list the catalog wants.
Walking `items` would give the same answer and more ways to get it wrong.

One call per query and the account is billed for it, so nothing here decides
*which* queries to pull — that is the caller's, and it is a cost.
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("organiciq.dataforseo")

ENDPOINT = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
TIMEOUT_SECONDS = 90.0

#: Google's US location code, and the default market for these clients.
DEFAULT_LOCATION_CODE = 2840
DEFAULT_LANGUAGE = "en"

#: Ten results is enough to see which features a SERP carries, and costs less
#: than a hundred. This is not a ranking pull — SE Ranking does that.
DEFAULT_DEPTH = 10

#: The features the catalog reasons about, in DataForSEO's own spelling.
AI_OVERVIEW = "ai_overview"
FEATURED_SNIPPET = "featured_snippet"


class DataForSeoError(RuntimeError):
    """A pull that did not land, in words somebody can act on."""


@dataclass(frozen=True)
class DataForSeoConfig:
    login: str
    password: str

    @property
    def auth_header(self) -> str:
        raw = f"{self.login}:{self.password}".encode()
        return "Basic " + base64.b64encode(raw).decode()


@dataclass(frozen=True)
class SerpFeatures:
    keyword: str
    #: Every element type on the SERP, held or not. The whole point.
    item_types: tuple[str, ...] = ()
    #: Domains holding each feature, where DataForSEO named one, so "the
    #: client does not hold it" is read rather than assumed.
    holders: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def holds(self, feature: str, domain: str) -> bool:
        target = domain.strip().lower().removeprefix("www.")
        return any(
            target in holder for holder in self.holders.get(feature, ())
        )


def load_config() -> DataForSeoConfig | None:
    login = (os.getenv("DATAFORSEO_LOGIN") or "").strip()
    password = (os.getenv("DATAFORSEO_PASSWORD") or "").strip()
    if not login or not password:
        return None
    return DataForSeoConfig(login=login, password=password)


def configured() -> bool:
    return load_config() is not None


def _domains(item: dict) -> list[str]:
    """Every domain an element names, however it spells it."""
    out: list[str] = []
    for key in ("domain", "source_domain"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            out.append(value.strip().lower().removeprefix("www."))
    for key in ("items", "references", "elements"):
        nested = item.get(key)
        if isinstance(nested, list):
            for child in nested:
                if isinstance(child, dict):
                    out.extend(_domains(child))
    return out


def parse(result: dict) -> SerpFeatures:
    """One SERP's features, from DataForSEO's own `item_types`."""
    item_types = tuple(
        t for t in (result.get("item_types") or []) if isinstance(t, str)
    )
    holders: dict[str, list[str]] = {}
    for item in result.get("items") or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if not isinstance(kind, str):
            continue
        found = _domains(item)
        if found:
            holders.setdefault(kind, []).extend(found)
    return SerpFeatures(
        keyword=result.get("keyword") or "",
        item_types=item_types,
        holders={k: tuple(sorted(set(v))) for k, v in holders.items()},
    )


def fetch(
    keyword: str,
    *,
    location_code: int = DEFAULT_LOCATION_CODE,
    language_code: str = DEFAULT_LANGUAGE,
    depth: int = DEFAULT_DEPTH,
    config: DataForSeoConfig | None = None,
    client: httpx.Client | None = None,
) -> SerpFeatures:
    """One query's SERP features. One call, and the account is billed for it."""
    config = config or load_config()
    if config is None:
        raise DataForSeoError(
            "DataForSEO is not configured. Set DATAFORSEO_LOGIN and "
            "DATAFORSEO_PASSWORD."
        )
    if not keyword.strip():
        raise DataForSeoError("A SERP pull needs a keyword.")

    # The body is an array of tasks even when there is only one.
    payload = [
        {
            "keyword": keyword,
            "location_code": location_code,
            "language_code": language_code,
            "depth": depth,
            "device": "desktop",
        }
    ]
    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = client.post(
            ENDPOINT,
            json=payload,
            headers={
                "Authorization": config.auth_header,
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        raise DataForSeoError(f"DataForSEO did not answer: {exc}") from exc
    finally:
        if owns_client:
            client.close()

    if response.status_code >= 400:
        raise DataForSeoError(
            f"DataForSEO refused the pull ({response.status_code}): "
            f"{response.text[:200]}"
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise DataForSeoError("DataForSEO returned something that was not JSON.") from exc

    # DataForSEO answers 200 with a per-task status, so the HTTP code alone
    # does not say the pull worked.
    tasks = body.get("tasks") or []
    if not tasks:
        raise DataForSeoError("DataForSEO returned no task.")
    task = tasks[0]
    code = task.get("status_code")
    if code != 20000:
        raise DataForSeoError(
            f"DataForSEO task failed ({code}): {task.get('status_message')}"
        )
    results = task.get("result") or []
    if not results:
        raise DataForSeoError(f"DataForSEO returned no SERP for “{keyword}”.")
    return parse(results[0])
