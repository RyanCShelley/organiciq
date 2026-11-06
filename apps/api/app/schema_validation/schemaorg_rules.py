"""Layer 1: is the markup valid Schema.org?

Everything is answered from the vocabulary file, never from a list kept by hand, and nothing here knows what Google does with a property.

Severity policy (Schema.org's own guidance is that a property's `domainIncludes` and `rangeIncludes` say what is *expected*, not what is forbidden, so a
mismatch there is a warning; a term that is not in the vocabulary at all is an error):

* a type or property that does not exist (or differs from one that does only by letter case): **error**
* a property used on a type whose ancestry the vocabulary does not list it for: **warning**
* a value of a kind the property's range does not list (a node of the wrong type, a malformed date): **warning**
* a type or property the vocabulary has superseded or moved to its attic: **informational**
* a type from outside Schema.org, or a prefixed property from another vocabulary: not judged
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.schema_validation import findings as F
from app.schema_validation.graph import KEYWORDS, Graph, Node, as_list
from app.schema_validation.vocabulary import Vocabulary

_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")  # a year, a month or a day: ISO 8601 allows each, and Schema.org and Google read them
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")
_TIME = re.compile(r"^\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")
_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_BOOL = {"true", "false", "http://schema.org/true", "https://schema.org/true", "http://schema.org/false", "https://schema.org/false"}


def snippet(value: Any, limit: int = 240) -> Any:
    """The markup's own value as evidence: kept as it is when it is short, and cut to a string when it is not."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return value if len(text) <= limit else text[: limit - 1] + "…"


def _joined(types: list[str]) -> str:
    return "/".join(types)


def _list(names: tuple[str, ...], n: int = 8) -> str:
    shown = ", ".join(names[:n])
    return shown + (f" and {len(names) - n} more" if len(names) > n else "")


def _literal_problem(vocab: Vocabulary, prop: str, value: str) -> str | None:
    """What is wrong with a text value for a property whose range is only data types of one strict kind, or None."""
    info = vocab.property(prop)
    if info is None or not info.ranges:
        return None
    ranges = set(info.ranges)
    if ranges & {"Text", "PronounceableText"} or any(not vocab.is_datatype(r) for r in ranges):
        return None  # free text is accepted, or a name where a thing is expected (consumers read it)
    text = value.strip()
    if ranges <= {"Date", "DateTime"} and not (_DATE.match(text) or _DATETIME.match(text)):
        return "a date (ISO 8601, like 2026-10-31, or a year like 2009)"
    if ranges == {"Time"} and not _TIME.match(text):
        return "a time (ISO 8601, like 09:30)"
    if ranges <= {"Number", "Integer", "Float"} and not _NUMBER.match(text):
        return "a number"
    if ranges == {"Boolean"} and text.lower() not in _BOOL:
        return "true or false"
    if ranges == {"URL"} and not text.startswith(("http://", "https://", "mailto:", "tel:", "ftp://")):
        return "a full address (https://…)"
    return None


def check(graph: Graph, vocab: Vocabulary) -> list[F.Finding]:
    out: list[F.Finding] = []

    def add(node: Node, **kw: Any) -> None:
        out.append(F.Finding(url=graph.url, entity_id=node.id or node.raw_id, layer="schemaorg", **kw))

    for node in graph.nodes:
        known: list[str] = []
        for raw in node.types:
            t = vocab.type_name(raw)
            if t:
                known.append(t)
                status, sup = vocab.type_status(t)
                if status == "deprecated":
                    add(node, rule_id="schemaorg.deprecated_type", category=F.INFORMATIONAL, type=t,
                        title=f"Type '{t}' is deprecated in Schema.org", message=f"'{t}' is deprecated" + (f"; use {_list(sup)}" if sup else ""),
                        explanation="Schema.org has retired this type. It still parses, so nothing breaks, but new markup should use its replacement.",
                        recommendation=(f"Use {_list(sup)} instead." if sup else "Use a current type."), doc=F.schema_doc(t), evidence={"@type": raw}, confidence="high")
                continue
            near = vocab.type_near_miss(raw)
            if near:
                add(node, rule_id="schemaorg.type_case", category=F.ERROR, type=raw,
                    title=f"Type '{raw}' should be written '{near}'",
                    message=f"'@type': '{raw}' is not a Schema.org type; '{near}' is (types are case-sensitive)",
                    explanation="Schema.org names are case-sensitive, so this type is not recognised and the node is read as having no type.",
                    recommendation=f"Change the type to '{near}'.", doc=F.schema_doc(near), evidence={"@type": raw}, auto_fixable=True, confidence="high")
            elif not vocab.term(raw)[1]:
                add(node, rule_id="schemaorg.unknown_type", category=F.WARNING, type=raw,
                    title=f"'{raw}' is not a Schema.org type",
                    message=f"'@type': '{raw}' is not in the Schema.org vocabulary (version {vocab.version})",
                    explanation="The type is not defined by Schema.org. It may be an extension defined in the page's @context, in which case it is valid for that vocabulary but not understood by search engines.",
                    recommendation="Use the closest Schema.org type, or confirm the extension is intended.", doc=F.SCHEMA_DOCS, evidence={"@type": raw}, confidence="medium")

        if not node.types:
            continue  # an untyped object is a value (a language-tagged string, a bare structure): there is nothing to judge a property against
        judge_domain = bool(known)

        for key, value in node.data.items():
            if key in KEYWORDS or key.startswith("@") or ":" in key:
                continue
            prop = vocab.property_name(key)
            if prop is None:
                if not judge_domain or vocab.action_annotation(key):
                    continue
                near = vocab.property_near_miss(key)
                if near:
                    add(node, rule_id="schemaorg.property_case", category=F.ERROR, type=_joined(known), property=key,
                        title=f"Property '{key}' should be written '{near}'",
                        message=f"'{key}' on {_joined(known)} is not a Schema.org property; '{near}' is (properties are case-sensitive)",
                        explanation="Property names are case-sensitive. A misspelt name is ignored by every consumer, so the value is lost.",
                        recommendation=f"Rename it to '{near}'.", doc=F.schema_doc(near), evidence={key: snippet(value)}, auto_fixable=True, confidence="high")
                else:
                    add(node, rule_id="schemaorg.unknown_property", category=F.ERROR, type=_joined(known), property=key,
                        title=f"'{key}' is not a Schema.org property",
                        message=f"'{key}' on {_joined(known)} does not exist in the Schema.org vocabulary (version {vocab.version})",
                        explanation="The property is not defined anywhere in Schema.org, so no consumer will read it. If a vocabulary from another source is intended, its terms need a prefix defined in the @context.",
                        recommendation="Remove it, or replace it with the Schema.org property that carries the same meaning.", doc=F.SCHEMA_DOCS, evidence={key: snippet(value)}, confidence="high")
                continue

            info = vocab.property(prop)
            assert info is not None
            if info.status == "deprecated":
                add(node, rule_id="schemaorg.deprecated_property", category=F.INFORMATIONAL, type=_joined(known) or _joined(node.types), property=prop,
                    title=f"Property '{prop}' is deprecated in Schema.org", message=f"'{prop}' is deprecated" + (f"; use {_list(info.superseded_by)}" if info.superseded_by else ""),
                    explanation="Schema.org has retired this property. It still parses, but new markup should use its replacement.",
                    recommendation=(f"Use {_list(info.superseded_by)} instead." if info.superseded_by else "Use a current property."), doc=F.schema_doc(prop), evidence={key: snippet(value)}, confidence="high")

            if info.status == "deprecated":
                continue  # already reported as deprecated; where a retired property may sit is not worth a second finding
            if judge_domain and not vocab.applies(prop, known):
                add(node, rule_id="schemaorg.property_domain", category=F.WARNING, type=_joined(known), property=prop,
                    title=f"'{prop}' is not defined on {_joined(known)}",
                    message=f"'{prop}' is defined on {_list(info.domains)}, none of which {_joined(known)} is or inherits from",
                    explanation=f"Schema.org lists the types a property is expected on. {_joined(known)} and the types above it are not among them, so consumers may ignore the value. "
                    "A property is accepted when any type above the node's type allows it (a Service inherits what Intangible and Thing define), which is not the case here.",
                    recommendation=f"Move '{prop}' to a node of one of those types, or use a property {_joined(known)} does support. Check what the surrounding graph means before moving it.",
                    doc=F.schema_doc(prop), evidence={key: snippet(value)}, confidence="high")

            for item in as_list(value):
                _range(graph, vocab, node, key, prop, known, item, out)
    return out


def _range(graph: Graph, vocab: Vocabulary, node: Node, key: str, prop: str, known: list[str], item: Any, out: list[F.Finding]) -> None:
    info = vocab.property(prop)
    if info is None or not info.ranges:
        return
    where = _joined(known) or _joined(node.types)

    def warn(kind: str, expected: str) -> None:
        out.append(F.Finding(
            url=graph.url, entity_id=node.id or node.raw_id, layer="schemaorg", rule_id="schemaorg.property_range", category=F.WARNING, type=where, property=prop,
            title=f"'{prop}' on {where} holds {kind}, but expects {expected}", message=f"'{prop}' holds {kind}; Schema.org expects {expected}",
            explanation="The property's range lists the kinds of value it takes. A value of another kind is usually misread or dropped.",
            recommendation=f"Change the value of '{prop}' to the kind Schema.org expects: {expected}.", doc=F.schema_doc(prop), evidence={key: snippet(item)}, confidence="medium",
        ))

    if isinstance(item, str):
        problem = _literal_problem(vocab, prop, item)
        if problem:
            warn("text that is not that", problem)
        return
    if not isinstance(item, dict) or "@value" in item:
        return
    node_ranges = tuple(r for r in info.ranges if not vocab.is_datatype(r))
    types: list[str] = []
    if set(item) == {"@id"}:
        target = graph.get(graph_id(graph, item["@id"]))
        types = [t for t in (vocab.type_name(x) for x in (target.types if target else [])) if t]
    else:
        types = [t for t in (vocab.type_name(x) for x in as_list(item.get("@type")) if isinstance(x, str)) if t]
    if not types:
        return  # a reference to something not on this page, or an untyped or custom-typed value: it cannot be judged
    if not node_ranges:
        warn(f"a {_joined(types)} node", "plain data (" + _list(info.ranges) + ")")
    elif not any(vocab.ancestors(t) & set(node_ranges) for t in types):
        warn(f"a {_joined(types)} node", _list(node_ranges))


def graph_id(graph: Graph, raw: str) -> str:
    from app.schema_validation.graph import absolute

    return absolute(raw, graph.url)
