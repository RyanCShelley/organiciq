"""The Schema.org vocabulary, as the schema validator reads it.

Loaded once from the versioned file in `data/` (built from Schema.org's own release by `scripts/build_schema_vocab.py`). Nothing here is a
hand-kept list of properties: whether a property applies to a type is answered from the vocabulary's `domainIncludes`, walking the type's
whole ancestry (`Service -> Intangible -> Thing`, `ImageObject -> MediaObject -> CreativeWork -> Thing`), across every `@type` a node carries.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).parent / "data"
VERSION = "30.1"

#: The ways markup names a Schema.org term: https://schema.org/Service, http://schema.org/Service, schema:Service, schema.org/Service, Service.
_IRI = re.compile(r"^(?:https?://(?:www\.)?schema\.org/|schema:)(?P<term>[^/#?]+)/?$", re.IGNORECASE)
#: Terms in the vocabulary reachable from a bare prefix other than schema (a vendor's own, or a full IRI elsewhere).
_FOREIGN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass(frozen=True)
class PropertyInfo:
    name: str
    domains: tuple[str, ...]
    ranges: tuple[str, ...]
    status: str | None
    superseded_by: tuple[str, ...]


class Vocabulary:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.version: str = raw["version"]
        self.source: str = raw["source"]
        self._types: dict[str, dict[str, Any]] = raw["types"]
        self._props: dict[str, dict[str, Any]] = raw["properties"]
        self._lower_props = {p.lower(): p for p in self._props}
        self._lower_types = {t.lower(): t for t in self._types}
        self._ancestors: dict[str, frozenset[str]] = {}
        # The vocabulary never changes once loaded, and an audit asks the same questions of the same few hundred names tens of thousands of times.
        self._type_names: dict[str, str | None] = {}
        self._infos: dict[str, PropertyInfo | None] = {}

    # ── names ────────────────────────────────────────────────────────────────

    @staticmethod
    @lru_cache(maxsize=8192)
    def term(value: str) -> tuple[str | None, bool]:
        """(the bare Schema.org term, whether the name is a foreign vocabulary's). 'https://schema.org/Service' and 'Service' both give 'Service'."""
        m = _IRI.match(value.strip())
        if m:
            return m.group("term"), False
        if _FOREIGN.match(value.strip()):
            return None, True
        return value.strip(), False

    def type_name(self, value: str) -> str | None:
        """The canonical Schema.org type for a markup @type, or None when it is not one (a foreign IRI, a custom or misspelt type)."""
        if value in self._type_names:
            return self._type_names[value]
        bare, foreign = self.term(value)
        found = None if foreign or bare is None else (bare if bare in self._types else None)
        if isinstance(value, str) and len(self._type_names) < 8192:
            self._type_names[value] = found
        return found

    def type_near_miss(self, value: str) -> str | None:
        """A type that differs only by letter case ('service' for 'Service'): markup is case-sensitive, so it is a mistake with an obvious fix."""
        bare, foreign = self.term(value)
        if foreign or bare is None or bare in self._types:
            return None
        return self._lower_types.get(bare.lower())

    def property_name(self, value: str) -> str | None:
        bare, foreign = self.term(value)
        if foreign or bare is None:
            return None
        return bare if bare in self._props else None

    def action_annotation(self, value: str) -> str | None:
        """The property a `<property>-input` or `<property>-output` key annotates, or None.

        Schema.org's Actions convention (https://schema.org/docs/actions.html) allows any property of an action to be described by a key with this suffix, such as
        `query-input` on a SearchAction. These are not in the vocabulary as terms and are valid.
        """
        for suffix in ("-input", "-output"):
            if value.endswith(suffix) and self.property_name(value[: -len(suffix)]):
                return value[: -len(suffix)]
        return None

    def property_near_miss(self, value: str) -> str | None:
        bare, foreign = self.term(value)
        if foreign or bare is None or bare in self._props:
            return None
        return self._lower_props.get(bare.lower())

    # ── types ────────────────────────────────────────────────────────────────

    def has_type(self, name: str) -> bool:
        return name in self._types

    def ancestors(self, name: str) -> frozenset[str]:
        """The type and every type above it, through every parent (multiple inheritance included)."""
        if name in self._ancestors:
            return self._ancestors[name]
        out: set[str] = {name}
        stack = [name]
        while stack:
            for parent in self._types.get(stack.pop(), {}).get("parents", ()):
                if parent not in out:
                    out.add(parent)
                    stack.append(parent)
        self._ancestors[name] = frozenset(out)
        return self._ancestors[name]

    def is_a(self, name: str, ancestor: str) -> bool:
        return ancestor in self.ancestors(name)

    def type_status(self, name: str) -> tuple[str | None, tuple[str, ...]]:
        t = self._types.get(name, {})
        return t.get("status"), tuple(t.get("superseded_by", ()))

    def is_datatype(self, name: str) -> bool:
        return bool(self._types.get(name, {}).get("datatype"))

    # ── properties ───────────────────────────────────────────────────────────

    def property(self, name: str) -> PropertyInfo | None:
        if name in self._infos:
            return self._infos[name]
        p = self._props.get(name)
        info = None if p is None else PropertyInfo(name, tuple(p["domains"]), tuple(p["ranges"]), p.get("status"), tuple(p.get("superseded_by", ())))
        if len(self._infos) < 8192:
            self._infos[name] = info
        return info

    def applies(self, prop: str, types: list[str]) -> bool:
        """Is the property defined on any of the node's types or on any type above one? A node with several @type values may use what any of them allows."""
        info = self._props.get(prop)
        if info is None:
            return False
        domains = set(info["domains"])
        return any(self.ancestors(t) & domains for t in types)

    def types_with(self, prop: str) -> tuple[str, ...]:
        info = self._props.get(prop)
        return tuple(info["domains"]) if info else ()

    def range_accepts_node(self, prop: str, node_types: list[str]) -> bool | None:
        """For a property whose value is a node: does one of its types fit the range? None when the range is only data types (so a node is not expected)
        or the node's types are not in the vocabulary (a custom type cannot be judged)."""
        info = self._props.get(prop)
        known = [t for t in node_types if t in self._types]
        if info is None or not known:
            return None
        ranges = [r for r in info["ranges"] if not self.is_datatype(r)]
        if not ranges:
            return False
        return any(self.ancestors(t) & set(ranges) for t in known)

    def range_accepts_literal(self, prop: str, value: Any) -> bool | None:
        """For a property whose value is plain data: is that kind of value among the range's data types? None when it cannot be judged (an unknown property)."""
        info = self._props.get(prop)
        if info is None:
            return None
        ranges = set(info["ranges"])
        datatypes = {r for r in ranges if self.is_datatype(r)}
        if isinstance(value, bool):
            return "Boolean" in datatypes or "Text" in datatypes
        if isinstance(value, (int, float)):
            # Markup often writes numbers as numbers where Schema.org says Text (a postal code, a phone number): that is accepted by consumers.
            return bool(datatypes & {"Number", "Integer", "Float", "Text", "QuantitativeValue"}) or bool(ranges - datatypes)
        if isinstance(value, str):
            # Anything can be written as text, and a name where a node is expected is common (Google reads it); only a boolean or number range is strict.
            return bool(datatypes & {"Text", "URL", "Date", "DateTime", "Time", "Number", "Integer", "Float", "Boolean", "PronounceableText", "CssSelectorType", "XPathType"}) or bool(ranges - datatypes)
        return None


@lru_cache(maxsize=1)
def load(version: str = VERSION) -> Vocabulary:
    path = DATA / f"schemaorg-{version}.json"
    return Vocabulary(json.loads(path.read_text()))
