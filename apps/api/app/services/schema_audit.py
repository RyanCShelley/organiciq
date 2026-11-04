"""Schema and knowledge graph: what structured data each page carries, what its kind of page should carry, and whether the brand
reads as one clear entity.

The page-by-page audit runs the Topic Hub tool's code (`app.schema_tools`): the kind of page is worked out from its address and
its markup, compared with the markup that kind should carry, and the markup it has is run through the cleanup that finds what to
correct. Model-written audits and markup are on demand, per page (`schema_pages`).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSchema, FactCrawlPageSnapshot
from app.models.schema_tools import ClientSchemaConcept, ClientSchemaIgnore
from app.schema_tools.expected import expected_for, find_missing_recommended, find_missing_required
from app.schema_tools.page_type import detect_page_type
from app.schema_tools.transforms import run_pipeline
from app.services.competitors import bare_domain
from app.services.site_health import is_pagination

LISTED = 150

#: In the order they are shown.
TYPE_LABELS: dict[str, str] = {
    "homepage": "Home page",
    "product": "Product pages",
    "productized_service": "Productized service pages",
    "service": "Service pages",
    "category": "Collection and category pages",
    "editorial": "Articles and blog posts",
    "faq": "FAQ pages",
    "documentation": "Guides and documentation",
    "about": "About and contact pages",
    "landing": "Landing pages",
    "generic": "Other pages",
}

_URL = re.compile(r"https?://\S+")


def collect_types(blocks: list[Any]) -> list[str]:
    """Distinct @type names across the blocks, @graph members included (the Topic Hub tool's rule)."""
    seen: set[str] = set()

    def visit(obj: object) -> None:
        if isinstance(obj, dict):
            t = obj.get("@type")
            for name in (t if isinstance(t, list) else [t]):
                if isinstance(name, str):
                    seen.add(name)
            graph = obj.get("@graph")
            if isinstance(graph, list):
                for g in graph:
                    visit(g)
        elif isinstance(obj, list):
            for item in obj:
                visit(item)

    for block in blocks:
        visit(block)
    return sorted(seen)


def merged_graph(blocks: list[Any]) -> Any:
    """The page's blocks as one graph, so the cleanup sees the whole picture (as the Topic Hub tool does)."""
    if len(blocks) == 1:
        return blocks[0]
    nodes: list[Any] = []
    for block in blocks:
        if isinstance(block, list):
            nodes += [i for i in block if isinstance(i, dict)]
        elif isinstance(block, dict):
            nodes += [i for i in block["@graph"] if isinstance(i, dict)] if isinstance(block.get("@graph"), list) else [block]
    return {"@graph": nodes}


def score(has_jsonld: bool, missing_required: list[str], missing_recommended: list[str], corrections: int) -> float:
    """0 to 1 for one page. No JSON-LD at all is 0; otherwise 1, less 0.4 for each missing required type, 0.1 for each missing
    recommended one, and 0.05 per correction (at most 0.3). The Topic Hub tool's formula."""
    if not has_jsonld:
        return 0.0
    value = 1.0 - 0.4 * len(missing_required) - 0.1 * len(missing_recommended) - min(0.3, 0.05 * corrections)
    return round(max(0.0, value), 3)


def _normal(detail: str) -> str:
    return _URL.sub("<address>", detail)


#: Types that are parts of a page's markup rather than the page's subject: an Offer inside a Product's `offers` counts as present, but
#: a Product named inside a Review does not make the page a product page.
_COMPONENTS = {"Offer", "AggregateOffer", "AggregateRating", "Review", "Person", "Organization", "ImageObject", "Brand", "Rating", "ContactPoint", "PostalAddress"}


def _component_types(blocks: list[Any]) -> set[str]:
    found: set[str] = set()

    def walk(node: Any, top: bool) -> None:
        if isinstance(node, list):
            for i in node:
                walk(i, top)
        elif isinstance(node, dict):
            if not top:
                t = node.get("@type")
                found.update(x for x in (t if isinstance(t, list) else [t]) if isinstance(x, str) and x in _COMPONENTS)
            for key, value in node.items():
                if key != "@graph":
                    walk(value, False)
                else:
                    walk(value, True)

    for b in blocks:
        walk(b, True)
    return found


def load_ignores(db: Session, client: Client) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for scope, key in db.query(ClientSchemaIgnore.scope, ClientSchemaIgnore.key).filter(ClientSchemaIgnore.client_id == client.id):
        out[scope].add(key)
    return out


def apply_ignores(a: dict[str, Any], ign: dict[str, set[str]]) -> dict[str, Any] | None:
    """The audit of one page without what a person has said does not apply. None when the whole page or its kind is ignored."""
    if a["url"] in ign["page"] or a["page_type"] in ign["page_type"]:
        return None
    pt = a["page_type"]
    a["missing_required"] = [t for t in a["missing_required"] if f"{pt}:{t}" not in ign["expect"]]
    a["missing_recommended"] = [t for t in a["missing_recommended"] if f"{pt}:{t}" not in ign["expect"]]
    a["corrections"] = [c for c in a["corrections"] if _normal(c["detail"]) not in ign["cleanup"]]
    a["score"] = score(a["has_markup"], a["missing_required"], a["missing_recommended"], len(a["corrections"]))
    return a


def audit_page(url: str, title: str | None, blocks: list[Any], micro: set[str]) -> dict[str, Any]:
    present = sorted(set(collect_types(blocks)) | _component_types(blocks) | micro)
    page_type = detect_page_type(url, present, title)
    missing_required = find_missing_required(page_type, present)
    missing_recommended = find_missing_recommended(page_type, present)
    corrections = run_pipeline(merged_graph(blocks))[1] if blocks else []
    return {
        "url": url, "page_type": page_type, "present": present, "present_jsonld": collect_types(blocks), "has_jsonld": bool(blocks), "has_markup": bool(blocks) or bool(micro),
        "missing_required": missing_required, "missing_recommended": missing_recommended, "corrections": corrections,
        "score": score(bool(blocks) or bool(micro), missing_required, missing_recommended, len(corrections)),
    }


def _scored(a: dict[str, Any]) -> bool:
    """A page nothing is expected of (an unclassified page with no markup) is not marked down for having none."""
    return not (a["page_type"] == "generic" and not a["has_markup"])


def _average(group: list[dict[str, Any]]) -> int | None:
    return round(100 * sum(a["score"] for a in group) / len(group)) if group else None


def audit(db: Session, client: Client) -> dict[str, Any] | None:
    snaps = db.query(FactCrawlPageSnapshot).filter(FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY).all()
    if not snaps:
        return None
    pages = [s for s in snaps if s.status_code and 200 <= s.status_code < 300 and s.indexable and not is_pagination(s.normalized_url)]
    rows = db.query(FactCrawlPageSchema).filter(FactCrawlPageSchema.client_id == client.id).all()
    blocks: dict[str, list[Any]] = defaultdict(list)
    micro: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r.syntax == "json_ld" and not r.parse_error and r.raw:
            blocks[r.normalized_url].append(r.raw)
        elif r.syntax != "json_ld" and r.schema_type:
            micro[r.normalized_url].add(r.schema_type)

    ign = load_ignores(db, client)
    audits = [
        a for a in (apply_ignores(audit_page(s.normalized_url, s.title, blocks.get(s.normalized_url, []), micro.get(s.normalized_url, set())), ign) for s in pages) if a is not None
    ]
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for a in audits:
        by_type[a["page_type"]].append(a)

    types = []
    for key, label in TYPE_LABELS.items():
        group = by_type.get(key, [])
        if not group:
            continue
        fix, recommended = [], []
        for a in group:
            bits = []
            if a["missing_required"]:
                bits.append("Missing " + ", ".join(a["missing_required"]))
            if a["corrections"]:
                bits.append(f"{len(a['corrections'])} cleanup{'s' if len(a['corrections']) != 1 else ''}: " + "; ".join(_normal(c["detail"]) for c in a["corrections"][:2]))
            if bits:
                fix.append({"url": a["url"], "text": " · ".join(bits)})
            elif a["missing_recommended"]:
                recommended.append({"url": a["url"], "text": "Worth adding: " + ", ".join(a["missing_recommended"])})
        spec = expected_for(key)
        expects = [t for t in spec["required"] if f"{key}:{t}" not in ign["expect"]]
        types.append(
            {
                "page_type": key, "label": label, "pages": len(group), "expects": expects, "recommended": [t for t in spec["recommended"] if f"{key}:{t}" not in ign["expect"]],
                "score": _average([a for a in group if _scored(a)]),
                "affected": len(fix), "items": fix[:LISTED],
                "recommended_affected": len(recommended), "recommended_items": recommended[:LISTED],
            }
        )

    # What recurs across pages: fixed once in the theme or template, it clears them all.
    recurring: Counter[str] = Counter()
    example: dict[str, str] = {}
    meta: dict[str, dict[str, str]] = {}
    for a in audits:
        for c in a["corrections"]:
            text = _normal(c["detail"])
            recurring[text] += 1
            example.setdefault(text, a["url"])
            meta.setdefault(text, {"scope": "cleanup", "key": text, "label": text})
    for a in audits:
        for t in a["missing_required"]:
            text = f"Missing {t} on {TYPE_LABELS.get(a['page_type'], a['page_type']).lower()}"
            recurring[text] += 1
            example.setdefault(text, a["url"])
            meta.setdefault(text, {"scope": "expect", "key": f"{a['page_type']}:{t}", "label": f"{TYPE_LABELS.get(a['page_type'], a['page_type'])}: {t} is not expected"})
    fixes = [{"text": t, "pages": n, "example": example[t], "ignore": meta[t]} for t, n in recurring.most_common(10) if n > 1]

    present: Counter[str] = Counter()
    for a in audits:
        for t in a["present"]:
            present[t] += 1
    invalid = [{"url": r.normalized_url, "error": (r.parse_error or "")[:200]} for r in rows if r.parse_error][:LISTED]
    with_markup = sum(1 for a in audits if a["has_jsonld"])
    entity = _entity(db, client, blocks, micro, ign["check"])
    return {
        "crawl_date": max(s.snapshot_date for s in snaps).isoformat(),
        "pages": len(pages), "with_markup": with_markup,
        "score": _average([a for a in audits if _scored(a)]) or 0,
        "cleanups": sum(len(a["corrections"]) for a in audits),
        "types": types, "fixes": fixes, "present": [{"type": t, "pages": n} for t, n in present.most_common()],
        "invalid": invalid, "entity": entity,
        "ignored": [{"id": str(i.id), "scope": i.scope, "key": i.key, "label": i.label or i.key} for i in db.query(ClientSchemaIgnore).filter(ClientSchemaIgnore.client_id == client.id).order_by(ClientSchemaIgnore.created_at)],
        "concepts": [_concept_out(c) for c in db.query(ClientSchemaConcept).filter(ClientSchemaConcept.client_id == client.id).order_by(ClientSchemaConcept.name)],
    }


def _concept_out(c: ClientSchemaConcept) -> dict[str, Any]:
    return {"id": str(c.id), "name": c.name, "qid": c.qid, "label": c.label, "description": c.description, "url": f"https://www.wikidata.org/wiki/{c.qid}"}


# ── the brand as an entity ───────────────────────────────────────────────────

_ORG_TYPES = {"Organization", "LocalBusiness", "Corporation", "OnlineStore", "Store", "ProfessionalService"}


def _norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _nodes(blocks: list[Any]) -> list[dict[str, Any]]:
    """Every typed object in the blocks, nested ones included (an article's publisher is an organization)."""
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for i in node:
                walk(i)
        elif isinstance(node, dict):
            if "@type" in node:
                found.append(node)
            for v in node.values():
                walk(v)

    for b in blocks:
        walk(b)
    return found


def _types(node: dict[str, Any]) -> set[str]:
    t = node.get("@type")
    return {str(x) for x in (t if isinstance(t, list) else [t]) if x}


def _has(node: dict[str, Any], prop: str) -> bool:
    return node.get(prop) not in (None, "", [], {})


def _entity(db: Session, client: Client, blocks: dict[str, list[Any]], micro: dict[str, set[str]], ignored_checks: set[str] | None = None) -> dict[str, Any]:
    """Does the markup describe the brand as one organization, tied to the profiles and the Wikidata item that identify it?"""
    from app.models.llm_visibility import ClientLlmSettings
    from app.schema_tools.transforms import extract_graph

    saved = db.query(ClientLlmSettings.brand_name).filter(ClientLlmSettings.client_id == client.id).scalar()
    brand = (saved or client.client_name or "").strip()
    standalone: list[dict[str, Any]] = []
    every: list[dict[str, Any]] = []
    for ents in blocks.values():
        standalone += [n for b in ents for n in extract_graph(b) if _types(n) & _ORG_TYPES]
        every += [n for n in _nodes(ents) if _types(n) & _ORG_TYPES]
    names: Counter[str] = Counter(n["name"].strip() for n in every if isinstance(n.get("name"), str) and n["name"].strip())
    micro_pages = sum(1 for ts in micro.values() if "Organization" in ts)
    best = max(standalone, key=lambda o: sum(_has(o, p) for p in ("name", "url", "logo", "sameAs", "contactPoint", "address", "telephone")), default=None)
    same_as = sorted({x for n in every for x in ([n["sameAs"]] if isinstance(n.get("sameAs"), str) else [v for v in (n.get("sameAs") or []) if isinstance(v, str)])})
    approved = db.query(ClientSchemaConcept).filter(ClientSchemaConcept.client_id == client.id).all()
    brand_concept = next((c for c in approved if _norm(c.name) == _norm(brand)), None)

    def check(key: str, label: str, status: str, detail: str, fix: str | None = None) -> dict[str, Any]:
        return {"key": key, "label": label, "status": status, "detail": detail, "fix": fix}

    checks = []
    if standalone:
        checks.append(check("org", "Organization markup (JSON-LD)", "pass", f"Found on {len({id(n) for n in standalone})} blocks."))
    elif every:
        checks.append(check("org", "Organization markup (JSON-LD)", "warn", "The organization only appears inside other markup (as an article's publisher), never as its own block describing the business.", "Generate the homepage markup below: it adds an Organization block."))
    elif micro_pages:
        checks.append(check("org", "Organization markup (JSON-LD)", "warn", f"Only as microdata on {micro_pages} pages. Search engines read it, but JSON-LD is the form they and AI crawlers prefer.", "Generate the homepage markup below: it adds an Organization block."))
    else:
        checks.append(check("org", "Organization markup (JSON-LD)", "fail", "No Organization markup found on any crawled page.", "Generate the homepage markup below."))
    distinct = {_norm(n) for n in names}
    if len(distinct) > 1:
        checks.append(check("names", "One name everywhere", "fail", "The markup names the organization differently: " + ", ".join(f"“{n}” on {c}" for n, c in names.most_common()) + ".", "Use one exact name in every block."))
    elif names:
        only = next(iter(names))
        ok = not brand or _norm(brand) in _norm(only) or _norm(only) in _norm(brand)
        checks.append(check("names", "One name everywhere", "pass" if ok else "warn", f"Every block says “{only}”." if ok else f"The markup says “{only}” but the brand is set as “{brand}”.", None if ok else "Make the markup and the brand name match."))
    else:
        checks.append(check("names", "One name everywhere", "warn", "No organization name was found to compare."))
    wikidata_linked = any("wikidata.org" in x for x in same_as)
    checks.append(check("wikidata", "Linked to its Wikidata item", "pass" if (wikidata_linked or brand_concept) else "fail",
                        f"Wikidata item {brand_concept.qid} approved for “{brand_concept.name}”." if brand_concept else ("The markup links to Wikidata." if wikidata_linked else "The brand is not tied to a Wikidata item. That item is how search engines and AI recognize the brand as one known entity."),
                        None if (wikidata_linked or brand_concept) else "Find the brand's Wikidata item below and approve it. If it has none, creating one is the first step."))
    checks.append(check("same_as", "Links to the brand's other profiles (sameAs)", "pass" if same_as else "fail",
                        f"{len(same_as)} linked: " + ", ".join(urlsplit(x).netloc.removeprefix("www.") for x in same_as[:6]) + "." if same_as else "No sameAs links. These tell search engines and AI that the social, directory and profile pages belong to this brand.",
                        None if same_as else "Add the brand's real profile URLs (LinkedIn, Facebook, Instagram, Google Business Profile) to the Organization block."))
    for key, label, props in (("logo", "Logo", ("logo",)), ("contact", "Contact details", ("contactPoint", "telephone", "address")), ("url", "Website address", ("url",))):
        present = best is not None and any(_has(best, p) for p in props)
        checks.append(check(key, label, "pass" if present else "fail" if best is not None else "warn", f"{label} is in the Organization block." if present else (f"{label} is missing from the Organization block." if best is not None else "There is no standalone Organization block to read."), None if present else f"Add {' or '.join(props)} to the Organization block."))
    products = [u for u, ents in blocks.items() if any("Product" in _types(n) for n in extract_graph_all(ents))]
    branded = [u for u in products if any(_has(n, "brand") for n in extract_graph_all(blocks[u]) if "Product" in _types(n))]
    if products:
        good = len(branded) >= 0.8 * len(products)
        checks.append(check("brand", "Products name their brand", "pass" if good else "warn", f"{len(branded)} of {len(products)} products carry a brand.", None if good else "Add the brand to each Product block so products tie back to the organization."))
    for c in checks:
        if c["key"] in (ignored_checks or set()):
            c["status"], c["fix"] = "ignored", None
    return {"brand": brand, "names": [{"name": n, "blocks": c} for n, c in names.most_common()], "same_as": same_as, "checks": checks}


def extract_graph_all(blocks: list[Any]) -> list[dict[str, Any]]:
    from app.schema_tools.transforms import extract_graph

    return [n for b in blocks for n in extract_graph(b)]
