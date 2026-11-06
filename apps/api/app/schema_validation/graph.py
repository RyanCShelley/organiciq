"""One page's JSON-LD as a graph.

Every block on the page is read, `@graph` members and nested objects included, and each node is indexed by its identifier made absolute
against the page's address, so `#organization` in one block and `https://site/page#organization` in another are the same node. A value
that is only `{"@id": ...}` is a reference to a node; anything with a type or properties of its own is a definition (and is indexed when it has an @id).

Nothing here judges the markup. It reports what the page defines, what it points at, and where the same identifier is defined more than once;
the rule modules decide what each of those means.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

#: Keys that describe the JSON-LD itself, not the thing.
KEYWORDS = frozenset({"@context", "@type", "@id", "@graph", "@vocab", "@reverse", "@language", "@value", "@index", "@list", "@set", "@base", "@nest", "@container", "@direction", "@included", "@version", "@protected", "@propagate", "@import"})
#: Guard against pathological markup: a page's JSON-LD is shallow, and a deeper tree is not worth following.
MAX_DEPTH = 40


@dataclass
class Node:
    """An object that defines a thing: it has a type or properties of its own, not just an @id."""

    id: str | None  # absolute, or None for a blank node
    raw_id: str | None
    types: list[str]
    data: dict[str, Any]
    block: int
    path: str
    top_level: bool  # a member of the block (or its @graph), not embedded in another node's property
    parent_property: str | None = None  # for an embedded node, the property it is the value of
    parent_types: list[str] = field(default_factory=list)


@dataclass
class Reference:
    """A value that is only {"@id": ...}."""

    id: str  # absolute
    raw_id: str
    block: int
    path: str
    prop: str
    owner_id: str | None
    owner_types: list[str]


@dataclass
class Graph:
    url: str
    origin: str
    nodes: list[Node] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    index: dict[str, list[Node]] = field(default_factory=dict)
    contexts: list[Any] = field(default_factory=list)
    skipped: int = 0  # blocks that were not a JSON object or array, and so held no nodes

    def defined(self, node_id: str) -> bool:
        return node_id in self.index

    def get(self, node_id: str) -> Node | None:
        found = self.index.get(node_id)
        return found[0] if found else None

    def is_local(self, node_id: str) -> bool:
        """The identifier is on this site: the page's own origin (a relative one or a fragment becomes that once made absolute)."""
        return urlsplit(node_id).netloc.lower() == urlsplit(self.origin).netloc.lower() if node_id.startswith(("http://", "https://")) else True


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value is None else [value])


def type_names(node: dict[str, Any]) -> list[str]:
    return [t for t in as_list(node.get("@type")) if isinstance(t, str)]


def absolute(raw: str, base: str) -> str:
    """An identifier made absolute. A blank node label (`_:b0`) stays as it is, and is local to the page."""
    if raw.startswith("_:"):
        return raw
    try:
        return urljoin(base, raw)
    except ValueError:
        return raw


def _is_reference(obj: dict[str, Any]) -> bool:
    return set(obj) == {"@id"} and isinstance(obj["@id"], str)


def build(url: str, blocks: list[Any]) -> Graph:
    parts = urlsplit(url)
    g = Graph(url=url, origin=f"{parts.scheme}://{parts.netloc}" if parts.netloc else "")

    def visit(value: Any, block: int, path: str, *, top: bool, prop: str | None, parent: Node | None, depth: int, base: str) -> None:
        if depth > MAX_DEPTH:
            return
        if isinstance(value, list):
            for i, item in enumerate(value):
                visit(item, block, f"{path}[{i}]", top=top, prop=prop, parent=parent, depth=depth + 1, base=base)
            return
        if not isinstance(value, dict):
            return
        if "@context" in value and value["@context"] not in g.contexts:
            g.contexts.append(value["@context"])
        local_base = base
        if isinstance(value.get("@base"), str):
            local_base = urljoin(base, value["@base"])
        if "@graph" in value and isinstance(value["@graph"], list):
            visit(value["@graph"], block, f"{path}.@graph", top=True, prop=None, parent=None, depth=depth + 1, base=local_base)
            # A container that also describes a thing of its own carries it alongside the graph.
            rest = {k: v for k, v in value.items() if k not in ("@graph", "@context")}
            if not rest:
                return
            value = rest
        if "@value" in value or "@list" in value or "@set" in value:
            for k in ("@list", "@set"):
                if k in value:
                    visit(value[k], block, f"{path}.{k}", top=False, prop=prop, parent=parent, depth=depth + 1, base=local_base)
            return
        if parent is not None and prop is not None and _is_reference(value):
            raw = value["@id"]
            g.references.append(Reference(absolute(raw, local_base), raw, block, path, prop, parent.id, parent.types))
            return
        raw_id = value.get("@id") if isinstance(value.get("@id"), str) else None
        node = Node(
            id=absolute(raw_id, local_base) if raw_id else None, raw_id=raw_id, types=type_names(value), data=value, block=block, path=path, top_level=top,
            parent_property=prop, parent_types=parent.types if parent else [],
        )
        g.nodes.append(node)
        if node.id:
            g.index.setdefault(node.id, []).append(node)
        for key, child in value.items():
            if key in KEYWORDS or not isinstance(child, (dict, list)):
                continue
            visit(child, block, f"{path}.{key}", top=False, prop=key, parent=node, depth=depth + 1, base=local_base)

    for i, block in enumerate(blocks):
        if isinstance(block, (dict, list)):
            visit(block, i, f"[{i}]", top=True, prop=None, parent=None, depth=0, base=url)
        else:
            g.skipped += 1
    return g
