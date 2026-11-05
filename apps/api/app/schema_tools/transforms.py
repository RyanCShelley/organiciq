"""Deterministic JSON-LD cleanup pipeline.

Each transform takes a flat list of nodes (the @graph) and returns
``(modified_graph, list_of_corrections)``. The driver in auditor.py wraps
each page's JSON-LD into a graph, runs every transform, and returns the
union of corrections.

Ported from the GEO Audit Tool (RyanCShelley/GEO-Audit-Tool) — breadcrumb
emission and recommendations are deliberately excluded.
"""

from __future__ import annotations

import copy
from typing import Any
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def find_nodes_by_type(graph: list[dict[str, Any]], *type_names: str) -> list[dict[str, Any]]:
    """Return nodes whose @type matches any of *type_names*."""
    out: list[dict[str, Any]] = []
    for node in graph:
        t = node.get("@type", "")
        types = [t] if isinstance(t, str) else t
        if any(tn in types for tn in type_names):
            out.append(node)
    return out


def extract_graph(data: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    """Normalise JSON-LD into a flat list of nodes (handles @graph or single doc)."""
    if isinstance(data, list):
        return [n for n in data if isinstance(n, dict)]
    if isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            return [n for n in data["@graph"] if isinstance(n, dict)]
        return [data]
    return []


def wrap_graph(
    nodes: list[dict[str, Any]], original: dict[str, Any] | list[Any]
) -> dict[str, Any] | list[Any]:
    """Re-wrap nodes into the original container shape."""
    if isinstance(original, dict) and "@graph" in original:
        out = copy.deepcopy(original)
        out["@graph"] = nodes
        return out
    if isinstance(original, list):
        return nodes
    if len(nodes) == 1:
        return nodes[0]
    return {"@graph": nodes}


# ---------------------------------------------------------------------------
# Transform 1: normalize logo
# ---------------------------------------------------------------------------


def normalize_logo(
    graph: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Convert bare logo strings into ImageObject nodes."""
    corrections: list[dict[str, str]] = []
    for node in graph:
        logo = node.get("logo")
        if isinstance(logo, str):
            node["logo"] = {"@type": "ImageObject", "url": logo}
            corrections.append(
                {
                    "transform": "normalize_logo",
                    "node_id": node.get("@id", "?"),
                    "detail": f"Converted bare logo string to ImageObject: {logo}",
                }
            )
    return graph, corrections


# ---------------------------------------------------------------------------
# Transform 2: ensure WebSite node
# ---------------------------------------------------------------------------


def ensure_website_node(
    graph: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Add a WebSite node when an Organization or page exists but no WebSite does."""
    corrections: list[dict[str, str]] = []
    websites = find_nodes_by_type(graph, "WebSite")
    if websites:
        return graph, corrections

    orgs = find_nodes_by_type(graph, "Organization", "ProfessionalService", "LocalBusiness")
    pages = find_nodes_by_type(
        graph, "WebPage", "ServicePage", "AboutPage", "ContactPage", "CollectionPage",
    )

    base_url: str | None = None
    org_id: str | None = None
    for org in orgs:
        url = org.get("url") or org.get("@id", "")
        if url:
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            org_id = org.get("@id")
            break

    if not base_url:
        for page in pages:
            url = page.get("url") or page.get("@id", "")
            if url:
                parsed = urlparse(url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                break

    if not base_url:
        return graph, corrections

    website_id = f"{base_url}/#website"
    website: dict[str, Any] = {
        "@type": "WebSite",
        "@id": website_id,
        "url": base_url,
        "name": base_url.split("//")[-1],
    }
    if org_id:
        website["publisher"] = {"@id": org_id}

    graph.append(website)
    corrections.append(
        {
            "transform": "ensure_website_node",
            "node_id": website_id,
            "detail": f"Added missing WebSite node: {website_id}",
        }
    )

    # Fix WebPage.isPartOf so it references the WebSite, not the Organization.
    for page in pages:
        is_part_of = page.get("isPartOf")
        if not is_part_of or (
            isinstance(is_part_of, dict) and is_part_of.get("@id") != website_id
        ):
            page["isPartOf"] = {"@id": website_id}
            corrections.append(
                {
                    "transform": "ensure_website_node",
                    "node_id": page.get("@id", "?"),
                    "detail": f"Set WebPage.isPartOf to {website_id}",
                }
            )

    return graph, corrections


# ---------------------------------------------------------------------------
# Transform 3: fix about placement
# ---------------------------------------------------------------------------


def fix_about_placement(
    graph: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Remove ``about`` from Service nodes and move it to the WebPage."""
    corrections: list[dict[str, str]] = []
    service_types = ("Service", "ProfessionalService", "FinancialService")
    services = find_nodes_by_type(graph, *service_types)
    pages = find_nodes_by_type(
        graph, "WebPage", "ServicePage", "AboutPage", "ContactPage", "CollectionPage",
    )

    moved_about: list[Any] = []
    for svc in services:
        about = svc.pop("about", None)
        if about is not None:
            corrections.append(
                {
                    "transform": "fix_about_placement",
                    "node_id": svc.get("@id", "?"),
                    "detail": "Removed 'about' from Service node — invalid per schema.org",
                }
            )
            if isinstance(about, list):
                moved_about.extend(about)
            else:
                moved_about.append(about)

    if moved_about and pages:
        page = pages[0]
        existing = page.get("about", [])
        if not isinstance(existing, list):
            existing = [existing] if existing else []
        existing.extend(moved_about)
        page["about"] = existing
        corrections.append(
            {
                "transform": "fix_about_placement",
                "node_id": page.get("@id", "?"),
                "detail": f"Moved {len(moved_about)} 'about' entries to WebPage where they belong",
            }
        )

    return graph, corrections


# ---------------------------------------------------------------------------
# Transform 4: set mainEntity
# ---------------------------------------------------------------------------


def set_main_entity(
    graph: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """If a WebPage and a Service exist, point WebPage.mainEntity → Service."""
    corrections: list[dict[str, str]] = []
    from app.schema_validation.vocabulary import load

    vocab = load()
    pages = find_nodes_by_type(graph, "WebPage", "ServicePage")
    # A business that provides a service (a ProfessionalService is an Organization) is not itself the page's service.
    services = [n for n in graph if any(vocab.is_a(vocab.type_name(t) or "", "Service") for t in ([n.get("@type")] if isinstance(n.get("@type"), str) else n.get("@type") or []))]

    if not pages or len(services) != 1:
        return graph, corrections

    service = services[0]
    service_id = service.get("@id")
    if not service_id:
        return graph, corrections

    page = pages[0]
    existing = page.get("mainEntity")
    if (
        existing
        and isinstance(existing, dict)
        and existing.get("@id") == service_id
    ):
        return graph, corrections

    page["mainEntity"] = {"@id": service_id}
    corrections.append(
        {
            "transform": "set_main_entity",
            "node_id": page.get("@id", "?"),
            "detail": f"Set WebPage.mainEntity to {service_id}",
        }
    )
    return graph, corrections


# ---------------------------------------------------------------------------
# Transform 5: validate properties against schema.org
# ---------------------------------------------------------------------------

_META_KEYS = frozenset({"@context", "@type", "@id", "@graph", "@vocab", "@reverse", "@language"})


def validate_properties(
    graph: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Strip properties that do not exist in Schema.org, from markup this tool generated.

    The test is the vocabulary itself (`app.schema_validation`), not a list kept by hand: a property is kept when Schema.org defines it, whatever type
    it is on. A property used on a type it is not defined for is *not* removed here (that is a judgement about meaning; the audit reports it and a person
    decides). Prefixed properties from another vocabulary, and nodes whose type is not a Schema.org type, are left alone.
    """
    from app.schema_validation.vocabulary import load

    vocab = load()
    corrections: list[dict[str, str]] = []
    for node in graph:
        node_type = node.get("@type", "")
        types = [node_type] if isinstance(node_type, str) else list(node_type)
        if not any(vocab.type_name(t) for t in types):
            continue
        for k in [k for k in node if k not in _META_KEYS and not k.startswith("@") and ":" not in k and vocab.property_name(k) is None and vocab.action_annotation(k) is None]:
            node.pop(k)
            corrections.append(
                {
                    "transform": "validate_properties",
                    "node_id": node.get("@id", "?"),
                    "detail": f"Removed '{k}' from {'/'.join(types)}: not a Schema.org property",
                }
            )
    return graph, corrections


# ---------------------------------------------------------------------------
# Transform 6: validate @id references
# ---------------------------------------------------------------------------


def validate_id_refs(
    graph: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Flag @id references to a local entity that nothing in the markup defines.

    Pure detection: the reference is left in place. Definitions are every node with an @id and properties of its own, nested ones included, so a node
    defined inside another counts. An identifier on Schema.org (an enumeration value) or on a site the markup does not define anything on is a
    legitimate reference, not a dangling one.
    """
    corrections: list[dict[str, str]] = []
    defined: set[str] = set()
    refs: list[tuple[str, str]] = []

    def walk(obj: object, path: str) -> None:
        if isinstance(obj, dict):
            ident = obj.get("@id")
            if isinstance(ident, str):
                if set(obj) == {"@id"}:
                    refs.append((ident, path))
                else:
                    defined.add(ident)
            for k, v in obj.items():
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    for node in graph:
        walk(node, node.get("@id", "root"))

    hosts = {urlparse(i).netloc.lower() for i in defined if i.startswith("http")}
    for ident, path in refs:
        if ident in defined or ident.startswith("_:"):
            continue
        local = ident.startswith("#") or (urlparse(ident).netloc.lower() in hosts)
        if local:
            corrections.append({"transform": "validate_id_refs", "node_id": path, "detail": f"Dangling @id reference: {ident} (at {path})"})
    return graph, corrections


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

TRANSFORMS = [
    normalize_logo,
    ensure_website_node,
    fix_about_placement,
    set_main_entity,
    validate_properties,
    validate_id_refs,
]


def run_pipeline(
    jsonld: dict[str, Any] | list[Any],
) -> tuple[dict[str, Any] | list[Any], list[dict[str, str]]]:
    """Run every transform on a JSON-LD object. Returns (cleaned, corrections)."""
    graph = extract_graph(copy.deepcopy(jsonld))
    all_corrections: list[dict[str, str]] = []

    for transform in TRANSFORMS:
        graph, corrections = transform(graph)
        all_corrections.extend(corrections)

    return wrap_graph(graph, jsonld), all_corrections
