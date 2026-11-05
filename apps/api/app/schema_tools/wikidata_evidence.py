"""What Wikidata knows about a candidate item, set beside what the site says, so the right item can be told from a namesake.

The name search (`wikidata.search_concept`) returns a label and one line. That does not separate "Corvant Solutions" from a fictional company of the same
name, so for each candidate this fetches the claims that identify an organization (official website, what it is an instance of, headquarters, industry,
profiles) and compares the ones the site can speak to. Nothing here chooses an item: it produces evidence and a verdict, and a person approves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.schema_tools.wikidata import DEFAULT_TIMEOUT, WIKIDATA_API, WIKIDATA_HEADERS

QID = re.compile(r"^Q\d+$")

# Properties read from an item.
P_WEBSITE, P_INSTANCE, P_HQ, P_INDUSTRY = "P856", "P31", "P159", "P452"
P_PROFILES = {"P4264": "https://www.linkedin.com/company/{}", "P2013": "https://www.facebook.com/{}", "P2003": "https://www.instagram.com/{}", "P2002": "https://twitter.com/{}"}


# Words that mark an item as an organization or business, in the labels of what it is an instance of. An item with none of them (a region, a genus, a person)
# is a namesake of an organization, not the organization.
ORG_WORDS = (
    "business", "company", "organization", "organisation", "corporation", "enterprise", "brand", "firm", "retailer", "manufacturer", "store", "shop", "agency",
    "nonprofit", "non-profit", "institution", "association", "startup", "start-up", "consultancy", "service", "provider", "publisher", "studio", "restaurant",
    "bank", "clinic", "hospital", "school", "university", "club", "foundation", "cooperative", "partnership", "subsidiary", "chain", "label", "maker", "producer",
    "operator", "platform", "marketplace", "website", "vendor", "distributor", "supplier", "wholesaler", "developer", "network", "group", "society", "union",
)


@dataclass
class Facts:
    """What the site's own markup says about the organization."""

    url: str | None = None
    types: list[str] = field(default_factory=list)
    places: list[str] = field(default_factory=list)  # address locality and region
    same_as: list[str] = field(default_factory=list)


def _host(url: str) -> str:
    return urlsplit(url if "//" in url else "//" + url).netloc.lower().removeprefix("www.")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _claims(entity: dict[str, Any], prop: str) -> list[Any]:
    out: list[Any] = []
    for c in (entity.get("claims") or {}).get(prop, []):
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if v is not None and c.get("rank") != "deprecated":
            out.append(v)
    return out


def _item_ids(entity: dict[str, Any], prop: str) -> list[str]:
    return [v["id"] for v in _claims(entity, prop) if isinstance(v, dict) and str(v.get("id", "")).startswith("Q")]


def referenced_ids(entities: dict[str, dict[str, Any]]) -> set[str]:
    return {i for e in entities.values() for p in (P_INSTANCE, P_HQ, P_INDUSTRY) for i in _item_ids(e, p)}


def compare(entity: dict[str, Any], labels: dict[str, str], facts: Facts) -> dict[str, Any]:
    """Rows of Wikidata against the site, and a verdict. `labels` names the items the entity points at."""

    def names(prop: str) -> list[str]:
        return [labels[i] for i in _item_ids(entity, prop) if i in labels]

    rows: list[dict[str, Any]] = []

    def add(key: str, label: str, wd: str, site: str, status: str) -> None:
        rows.append({"key": key, "label": label, "wikidata": wd or "none", "site": site or "not stated", "status": status})

    # Official website: the strongest single signal.
    urls = [v for v in _claims(entity, P_WEBSITE) if isinstance(v, str)]
    if not urls:
        add("website", "Official website", "", facts.url or "", "none")
    elif facts.url and any(_host(u) == _host(facts.url) for u in urls):
        add("website", "Official website", ", ".join(_host(u) for u in urls[:2]), _host(facts.url), "match")
    elif facts.url:
        add("website", "Official website", ", ".join(_host(u) for u in urls[:2]), _host(facts.url), "conflict")
    else:
        add("website", "Official website", ", ".join(_host(u) for u in urls[:2]), "", "none")

    # What it is: a fictional or non-organization item is a namesake.
    kinds = names(P_INSTANCE)
    site_types = ", ".join(facts.types)
    if not kinds:
        add("instance", "Instance of", "", site_types, "none")
    elif any("fictional" in k.lower() for k in kinds) or (not any(w in k.lower() for k in kinds for w in ORG_WORDS)):
        add("instance", "Instance of", ", ".join(kinds[:3]), site_types, "conflict")
    else:
        add("instance", "Instance of", ", ".join(kinds[:3]), site_types, "match" if site_types else "none")

    # Headquarters against the address in the markup.
    hq = names(P_HQ)
    if not hq:
        add("hq", "Headquarters", "", ", ".join(facts.places), "none")
    elif not facts.places:
        add("hq", "Headquarters", ", ".join(hq[:2]), "", "none")
    else:
        same = any(_norm(p) and (_norm(p) in _norm(h) or _norm(h) in _norm(p)) for p in facts.places for h in hq)
        add("hq", "Headquarters", ", ".join(hq[:2]), ", ".join(facts.places), "match" if same else "conflict")

    # Industry: shown as context; the markup does not state one to compare.
    add("industry", "Industry", ", ".join(names(P_INDUSTRY)[:3]), "", "info")

    # Profiles the item lists, against the sameAs the markup carries.
    # The first value of each is the preferred one; the rest are regional or product accounts.
    profiles = [tmpl.format(vs[0]) for prop, tmpl in P_PROFILES.items() if (vs := [v for v in _claims(entity, prop) if isinstance(v, str)])]
    if profiles:
        site_hosts = {(_host(u), _norm(urlsplit(u).path)) for u in facts.same_as}
        shared = [p for p in profiles if (_host(p), _norm(urlsplit(p).path)) in site_hosts]
        add("profiles", "Profiles on the item", ", ".join(_host(p).split(".")[0] for p in profiles[:4]), ", ".join(_host(u).split(".")[0] for u in facts.same_as[:4]),
            "match" if shared else "missing")
    else:
        add("profiles", "Profiles on the item", "", ", ".join(_host(u).split(".")[0] for u in facts.same_as[:4]), "none")

    scored = [r for r in rows if r["status"] in ("match", "conflict")]
    matched = sum(1 for r in scored if r["status"] == "match")
    conflicts = len(scored) - matched
    checked = sum(1 for r in rows if r["wikidata"] != "none")
    wrong_kind = any(r["key"] == "instance" and r["status"] == "conflict" for r in rows)
    if wrong_kind or (conflicts and not matched):
        verdict = "unlikely"
    elif matched >= 2 and not conflicts:
        verdict = "strong"
    elif conflicts:
        verdict = "weak"
    else:
        verdict = "possible"
    return {"rows": rows, "matched": matched, "checked": checked, "conflicts": conflicts, "verdict": verdict, "profiles": profiles}


async def fetch_entities(qids: list[str], *, client: httpx.AsyncClient, props: str = "claims|labels|descriptions") -> dict[str, dict[str, Any]]:
    """The items' claims and English labels. Missing items are left out."""
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(qids), 50):
        r = await client.get(WIKIDATA_API, params={"action": "wbgetentities", "ids": "|".join(qids[i : i + 50]), "props": props, "languages": "en", "format": "json"})
        r.raise_for_status()
        for qid, e in (r.json().get("entities") or {}).items():
            if isinstance(e, dict) and "missing" not in e:
                out[qid] = e
    return out


def _label(e: dict[str, Any]) -> str:
    return str(((e.get("labels") or {}).get("en") or {}).get("value") or e.get("id") or "")


def _description(e: dict[str, Any]) -> str:
    return str(((e.get("descriptions") or {}).get("en") or {}).get("value") or "")


async def evidence_for(qids: list[str], facts: Facts, *, timeout: float = DEFAULT_TIMEOUT) -> dict[str, dict[str, Any]]:
    """For each QID: its label, description and the comparison with the site. A QID Wikidata does not return is left out."""
    if not qids:
        return {}
    async with httpx.AsyncClient(timeout=timeout, headers=WIKIDATA_HEADERS) as client:
        entities = await fetch_entities(sorted(set(qids)), client=client)
        refs = sorted(referenced_ids(entities))
        named = await fetch_entities(refs, client=client, props="labels") if refs else {}
    labels = {q: _label(e) for q, e in named.items()}
    return {q: {"label": _label(e), "description": _description(e), "evidence": compare(e, labels, facts)} for q, e in entities.items()}
