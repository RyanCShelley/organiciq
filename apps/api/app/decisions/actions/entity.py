"""5a — the structured data that says who the brand is.

Answer engines identify a brand from its Organization markup. When three
pages give three different names, or the logo is missing from the one
block an engine is most likely to read, the site is not wrong so much as
unidentifiable — and no amount of content work fixes that.

Deliberately narrow. Article types, page-type mismatches and parse errors
are not here: those are on-page review work the plan already covers, and
folding them in would turn an hour's correction into an audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

#: The blocks that say who the brand is.
ENTITY_TYPES = frozenset({"Organization", "LocalBusiness", "ProfessionalService"})

#: What the homepage block has to carry for an engine to use it.
REQUIRED_HOMEPAGE = ("name", "url", "logo", "sameAs")
REQUIRED_LOCAL = ("address", "telephone")


@dataclass(frozen=True)
class EntityBlock:
    url: str
    schema_type: str
    raw: dict[str, Any]
    is_homepage: bool = False


@dataclass
class EntityFailure:
    check: str
    detail: str
    urls: list[str] = field(default_factory=list)


def _text(value: Any) -> str:
    """One value from something that may be a list, a dict or a string."""
    if isinstance(value, list):
        return _text(value[0]) if value else ""
    if isinstance(value, dict):
        return str(value.get("name") or value.get("url") or "")
    return str(value or "").strip()


def _present(raw: dict[str, Any], key: str) -> bool:
    value = raw.get(key)
    if isinstance(value, (list, dict)):
        return bool(value)
    return bool(str(value or "").strip())


def check_entity(blocks: list[EntityBlock], *, domain: str) -> list[EntityFailure]:
    """Everything wrong with how the site states who it is."""
    failures: list[EntityFailure] = []
    entity = [b for b in blocks if b.schema_type in ENTITY_TYPES]
    if not entity:
        return failures

    # 1. One name. Several is the failure that matters most: an engine
    #    cannot decide which brand it is reading about.
    names = {}
    for block in entity:
        name = _text(block.raw.get("name"))
        if name:
            names.setdefault(name, []).append(block.url)
    if len(names) > 1:
        failures.append(
            EntityFailure(
                check="name_conflict",
                detail="The site calls itself "
                + ", ".join(f"“{name}”" for name in sorted(names))
                + ". Pick one and use it in every Organization block.",
                urls=[url for urls in names.values() for url in urls][:20],
            )
        )

    # 2. The url property should point at this site. Pointing elsewhere
    #    hands the identity to whoever owns that host.
    host = (domain or "").strip().lower().removeprefix("www.").split("/", 1)[0]
    wrong_host = [
        block.url
        for block in entity
        if (declared := _text(block.raw.get("url")))
        and (urlsplit(declared).hostname or "").lower().removeprefix("www.") != host
    ]
    if wrong_host:
        failures.append(
            EntityFailure(
                check="url_host",
                detail=f"The `url` property does not point at {host}.",
                urls=wrong_host[:20],
            )
        )

    # 3. The homepage block is the one an engine is most likely to read.
    homepage = [b for b in entity if b.is_homepage]
    for block in homepage:
        required = list(REQUIRED_HOMEPAGE)
        if block.schema_type in {"LocalBusiness", "ProfessionalService"}:
            required += list(REQUIRED_LOCAL)
        missing = [key for key in required if not _present(block.raw, key)]
        if missing:
            failures.append(
                EntityFailure(
                    check="homepage_properties",
                    detail="The homepage "
                    f"{block.schema_type} block is missing "
                    + ", ".join(f"`{key}`" for key in missing)
                    + ".",
                    urls=[block.url],
                )
            )
    return failures
