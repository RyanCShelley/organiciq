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
#: Labs answers a big domain slowly: a ranked-keywords request that filters and
#: sorts a large site ran past 90 seconds in production. A request that times
#: out may still be billed, so the answer is a longer wait and fewer rows, not
#: a retry.
LABS_TIMEOUT_SECONDS = 240.0

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


class DataForSeoAuthError(DataForSeoError):
    """The credentials were rejected.

    Its own type because it is the one failure that will not come right on
    the next keyword: every remaining call in the run would fail the same
    way. Setting the variables to the placeholders out of a README reads as
    configured and fails 425 times, which is how it was found.
    """


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


def _post_task(
    url: str,
    payload: list[dict],
    *,
    config: DataForSeoConfig | None = None,
    client: httpx.Client | None = None,
    timeout: float = TIMEOUT_SECONDS,
) -> dict:
    """POST one task and return it once DataForSEO says it worked.

    DataForSEO answers 200 with a per-task status, so the HTTP code alone does
    not say a pull worked. Every endpoint here is billed per call.
    """
    config = config or load_config()
    if config is None:
        raise DataForSeoError(
            "DataForSEO is not configured. Set DATAFORSEO_LOGIN and "
            "DATAFORSEO_PASSWORD."
        )
    owns_client = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        response = client.post(
            url,
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

    if response.status_code in (401, 403):
        raise DataForSeoAuthError(
            "DataForSEO rejected the credentials. Check DATAFORSEO_LOGIN and "
            "DATAFORSEO_PASSWORD — the API password is generated in the API "
            "Access tab and is not the account password."
        )
    if response.status_code >= 400:
        raise DataForSeoError(
            f"DataForSEO refused the pull ({response.status_code}): "
            f"{response.text[:200]}"
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise DataForSeoError("DataForSEO returned something that was not JSON.") from exc

    tasks = body.get("tasks") or []
    if not tasks:
        raise DataForSeoError("DataForSEO returned no task.")
    task = tasks[0]
    code = task.get("status_code")
    # 401xx is their authentication range, and it arrives inside a 200 as
    # readily as it does as an HTTP status.
    if isinstance(code, int) and 40100 <= code < 40200:
        raise DataForSeoAuthError(
            f"DataForSEO rejected the credentials ({code}): "
            f"{task.get('status_message')}"
        )
    if code != 20000:
        raise DataForSeoError(
            f"DataForSEO task failed ({code}): {task.get('status_message')}"
        )
    return task


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
            # Without this the AI Overview comes back as a type with no
            # references, so "the client does not hold it" would be a
            # consequence of not having looked — on the one feature where
            # that matters most.
            "load_async_ai_overview": True,
        }
    ]
    task = _post_task(ENDPOINT, payload, config=config, client=client)
    results = task.get("result") or []
    if not results:
        raise DataForSeoError(f"DataForSEO returned no SERP for “{keyword}”.")
    return parse(results[0])


# --- Labs: a domain's rankings and keyword market data -----------------------
#
# Billed per request plus per row returned (about $0.012 + $0.00012 a row on
# the Labs rate card, so a 1,000-row competitor pull is about $0.13). Callers
# bound the rows; nothing here pages.

LABS = "https://api.dataforseo.com/v3/dataforseo_labs/google"
RANKED_KEYWORDS_ENDPOINT = f"{LABS}/ranked_keywords/live"
KEYWORD_OVERVIEW_ENDPOINT = f"{LABS}/keyword_overview/live"

#: Documented ceilings: 1,000 rows a ranked-keywords request and 700 keywords
#: (each at most 80 characters and 10 words) a keyword-overview request.
RANKED_KEYWORDS_MAX = 1000
KEYWORD_OVERVIEW_BATCH = 700
KEYWORD_MAX_CHARS = 80
KEYWORD_MAX_WORDS = 10

#: A client's `primary_market`, as `resolve_source` normalises it, to Google's
#: location code and the language to ask in.
MARKETS: dict[str, tuple[int, str]] = {
    "us": (2840, "en"),
    "uk": (2826, "en"),
    "ca": (2124, "en"),
    "au": (2036, "en"),
}


def market(source: str) -> tuple[int, str]:
    return MARKETS.get(source, MARKETS["us"])


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def ranked_keywords(
    domain: str,
    *,
    source: str = "us",
    max_position: int = 10,
    limit: int = RANKED_KEYWORDS_MAX,
    config: DataForSeoConfig | None = None,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Organic keywords a domain ranks for at `max_position` or better, biggest first.

    One request. Rows are `{keyword, position, volume, difficulty, cpc, url}`,
    the shape the competitor job stores, whichever vendor supplied them.
    """
    location_code, language_code = market(source)
    payload = [
        {
            "target": domain,
            "location_code": location_code,
            "language_code": language_code,
            "item_types": ["organic"],
            "limit": min(int(limit), RANKED_KEYWORDS_MAX),
            "filters": [["ranked_serp_element.serp_item.rank_group", "<=", max_position]],
            "order_by": ["keyword_data.keyword_info.search_volume,desc"],
        }
    ]
    task = _post_task(
        RANKED_KEYWORDS_ENDPOINT, payload, config=config, client=client, timeout=LABS_TIMEOUT_SECONDS
    )
    results = task.get("result") or []
    items = (results[0].get("items") if results else None) or []
    rows: list[dict] = []
    for item in items:
        data = item.get("keyword_data") or {}
        element = (item.get("ranked_serp_element") or {}).get("serp_item") or {}
        keyword = str(data.get("keyword") or "").strip()
        if not keyword:
            continue
        info = data.get("keyword_info") or {}
        rows.append(
            {
                "keyword": keyword,
                "position": _number(element.get("rank_group")),
                "volume": _number(info.get("search_volume")),
                "difficulty": _number((data.get("keyword_properties") or {}).get("keyword_difficulty")),
                "cpc": _number(info.get("cpc")),
                "url": element.get("url"),
            }
        )
    return rows


def keyword_overview(
    keywords: list[str],
    *,
    source: str = "us",
    config: DataForSeoConfig | None = None,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Volume, difficulty, CPC and intent for arbitrary keywords.

    Rows are `{keyword, volume, difficulty, cpc, competition, intents,
    is_data_found}`. A keyword DataForSEO has no data for is omitted from its
    answer and not billed; it comes back here with `is_data_found` false, so the
    caller records the answer instead of asking again next month.

    A keyword over their limits (80 characters, 10 words) cannot be asked
    about, so it is returned as not found rather than failing the batch.
    """
    location_code, language_code = market(source)
    unique = list(dict.fromkeys(k.strip() for k in keywords if k and k.strip()))
    askable = [
        k for k in unique if len(k) <= KEYWORD_MAX_CHARS and len(k.split()) <= KEYWORD_MAX_WORDS
    ]
    found: dict[str, dict] = {}
    for start in range(0, len(askable), KEYWORD_OVERVIEW_BATCH):
        batch = askable[start : start + KEYWORD_OVERVIEW_BATCH]
        task = _post_task(
            KEYWORD_OVERVIEW_ENDPOINT,
            [{"keywords": batch, "location_code": location_code, "language_code": language_code}],
            config=config,
            client=client,
            timeout=LABS_TIMEOUT_SECONDS,
        )
        results = task.get("result") or []
        for item in (results[0].get("items") if results else None) or []:
            keyword = str(item.get("keyword") or "").strip()
            if not keyword:
                continue
            info = item.get("keyword_info") or {}
            intent = (item.get("search_intent_info") or {}).get("main_intent")
            found[keyword.lower()] = {
                "keyword": keyword,
                "volume": _number(info.get("search_volume")),
                "difficulty": _number((item.get("keyword_properties") or {}).get("keyword_difficulty")),
                "cpc": _number(info.get("cpc")),
                "competition": _number(info.get("competition")),
                "intents": [intent] if intent else None,
                "is_data_found": True,
            }
    return [
        found.get(k.lower())
        or {
            "keyword": k,
            "volume": None,
            "difficulty": None,
            "cpc": None,
            "competition": None,
            "intents": None,
            "is_data_found": False,
        }
        for k in unique
    ]
