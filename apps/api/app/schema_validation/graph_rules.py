"""Layer 2 (graph): do the entities in the page's JSON-LD hold together?

A reference is judged against everything the page defines, in every block and every nesting, with identifiers made absolute. A reference with no
definition on the page is not automatically wrong:

* an identifier on Schema.org itself (`https://schema.org/InStock`) is a vocabulary term, not an entity;
* an identifier on another site (Wikidata, a profile, a partner) is an **external reference**: valid, and only worth checking if it should resolve;
* an identifier on this site that another crawled page defines is **defined elsewhere**: valid JSON-LD, but search engines read each page on its own,
  so this page's markup does not stand alone;
* an identifier on this site that nothing defines is a **dangling local reference**: the one real problem.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from app.schema_validation import findings as F
from app.schema_validation.graph import KEYWORDS, Graph, Node, absolute, as_list
from app.schema_validation.schemaorg_rules import snippet
from app.schema_validation.vocabulary import Vocabulary

_VOCAB_HOSTS = {"schema.org", "www.schema.org"}


def _is_vocabulary_term(node_id: str) -> bool:
    return urlsplit(node_id).netloc.lower() in _VOCAB_HOSTS


def _canon(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc.lower()}{p.path.rstrip('/')}"


def _same_page(a: str, b: str) -> bool:
    return _canon(a) == _canon(b)


def _norm_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def check(graph: Graph, vocab: Vocabulary, *, site_ids: dict[str, int] | None = None) -> list[F.Finding]:
    """`site_ids` maps an identifier to how many crawled pages define it, when the audit has looked across the site (None when it has not)."""
    out: list[F.Finding] = []

    def add(**kw: Any) -> None:
        out.append(F.Finding(url=graph.url, layer="graph", **kw))

    # ── the JSON-LD itself ──────────────────────────────────────────────────
    if graph.skipped:
        add(rule_id="graph.not_a_node", category=F.INFORMATIONAL, title="A JSON-LD block holds neither an object nor a list",
            message=f"{graph.skipped} JSON-LD block(s) are not an object or a list, so they hold no entities", explanation="The block parsed as JSON but is not JSON-LD.",
            recommendation="Check what the block was meant to carry.", doc=F.SCHEMA_DOCS, confidence="high")
    if graph.nodes and not graph.contexts:
        add(rule_id="graph.missing_context", category=F.ERROR, title="JSON-LD has no @context", message="None of the page's JSON-LD blocks declares an @context",
            explanation="Without a context the keys are not tied to Schema.org, so search engines do not read the markup as structured data.",
            recommendation='Add "@context": "https://schema.org" to the block.', doc=F.GOOGLE_INTRO, confidence="high", auto_fixable=True)
    for ctx in graph.contexts:
        for entry in as_list(ctx):
            if isinstance(entry, str) and urlsplit(entry).netloc.lower() not in _VOCAB_HOSTS:
                add(rule_id="graph.remote_context", category=F.WARNING, title="JSON-LD uses a remote @context other than Schema.org",
                    message=f"@context points at {entry}", explanation="A context fetched from another address has to be downloaded and parsed to read the markup, and search engines do not do that. "
                    "Properties defined there are not understood as Schema.org.", recommendation="Use https://schema.org as the context, adding a vocabulary only if it is needed.",
                    doc=F.SCHEMA_DOCS, evidence={"@context": entry}, confidence="medium")

    # ── references ──────────────────────────────────────────────────────────
    for ref in graph.references:
        if graph.defined(ref.id) or _is_vocabulary_term(ref.id):
            continue
        owner = "/".join(ref.owner_types) or None
        common = dict(entity_id=ref.owner_id, type=owner, property=ref.prop, evidence={ref.prop: {"@id": ref.raw_id}})
        if not graph.is_local(ref.id):
            add(rule_id="graph.external_reference", category=F.INFORMATIONAL, title=f"'{ref.prop}' refers to an identifier outside the site",
                message=f"'{ref.prop}' points at {ref.id}, which this page does not define", explanation="An identifier on another site is a legitimate way to name a thing (a Wikidata item, a partner's page). "
                "It is not defined here and cannot be checked from here.", recommendation="No change needed unless the identifier should resolve to a description; verify it if it matters.",
                doc=F.SCHEMA_DOCS, confidence="high", **common)
        elif site_ids is not None and site_ids.get(ref.id):
            add(rule_id="graph.defined_elsewhere", category=F.INFORMATIONAL, title=f"'{ref.prop}' refers to an entity another page defines",
                message=f"'{ref.prop}' points at {ref.id}, which is defined on {site_ids[ref.id]} other page(s) of the site, not on this one",
                explanation="The reference is valid JSON-LD, but search engines read each page's markup on its own and do not follow the identifier to another page, so this page's markup does not describe the entity.",
                recommendation="If the entity matters for this page, define it here (a full node with the same @id) instead of only pointing at it.", doc=F.GOOGLE_INTRO, confidence="medium", **common)
        else:
            known = "nowhere on the crawled site" if site_ids is not None else "not on this page (other pages were not checked)"
            add(rule_id="graph.dangling_reference", category=F.WARNING, title=f"'{ref.prop}' refers to a local entity that is not defined",
                message=f"'{ref.prop}' points at {ref.id}, which is defined {known}",
                explanation="The identifier is on this site, but no node with it exists in any of the page's blocks" + (" or on any other crawled page" if site_ids is not None else "")
                + ". The reference leads nowhere, so the relationship is lost.", recommendation="Define the entity (a node with this @id), or correct the identifier if it is misspelt.",
                doc=F.SCHEMA_DOCS, confidence="high" if site_ids is not None else "medium", **common)

    # ── the same identifier defined more than once ──────────────────────────
    for node_id, defs in graph.index.items():
        if len(defs) < 2:
            continue
        keys = {k for d in defs for k in d.data if k not in KEYWORDS and not k.startswith("@")}
        conflicts = []
        for k in sorted(keys):
            values = {_norm_value(d.data[k]) for d in defs if k in d.data}
            if sum(1 for d in defs if k in d.data) >= 2 and len(values) > 1:
                conflicts.append(k)
        types = sorted({t for d in defs for t in d.types})
        base = dict(entity_id=node_id, type="/".join(types) or None)
        if conflicts:
            add(rule_id="graph.conflicting_definitions", category=F.WARNING, title="The same @id is defined more than once with different values",
                message=f"{node_id} is defined {len(defs)} times and disagrees on: {', '.join(conflicts)}", explanation="JSON-LD merges nodes that share an @id, so conflicting values are all attached to one entity. "
                "A single-valued property such as name or telephone then has several answers and consumers pick one unpredictably.", recommendation="Keep one definition, or make the values agree.",
                doc=F.SCHEMA_DOCS, evidence={k: [snippet(d.data[k], 80) for d in defs if k in d.data] for k in conflicts[:3]}, confidence="high", **base)
        else:
            add(rule_id="graph.duplicate_definition", category=F.INFORMATIONAL, title="The same @id is defined in more than one place",
                message=f"{node_id} is defined {len(defs)} times (the definitions agree)", explanation="The definitions merge into one entity, so nothing is wrong; it only repeats markup.",
                recommendation="Keep one definition and refer to it by @id elsewhere.", doc=F.SCHEMA_DOCS, confidence="high", **base)

    # ── several organizations ───────────────────────────────────────────────
    orgs = [n for n in graph.nodes if any(vocab.is_a(vocab.type_name(t) or "", "Organization") for t in n.types)]
    ids = sorted({n.id for n in orgs if n.id})
    if len(ids) >= 2:
        add(rule_id="graph.multiple_organizations", category=F.INFORMATIONAL, title="The page defines several different Organization entities",
            message=f"{len(ids)} Organization nodes with different @id values: " + ", ".join(ids[:4]), explanation="A page can legitimately describe more than one organization (the publisher and a partner). "
            "When it is the same organization under two identifiers, search engines see two entities.", recommendation="If they are one organization, use one @id everywhere it is mentioned.",
            doc=F.SCHEMA_DOCS, evidence=ids[:4], confidence="medium", type="Organization")

    # ── relationships ───────────────────────────────────────────────────────
    for node in graph.nodes:
        _relationships(graph, vocab, node, add)
    return out


def _target_types(graph: Graph, vocab: Vocabulary, value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    if set(value) == {"@id"}:
        target = graph.get(absolute(value["@id"], graph.url))
        raw = target.types if target else []
    else:
        raw = [t for t in as_list(value.get("@type")) if isinstance(t, str)]
    return [t for t in (vocab.type_name(x) for x in raw) if t]


def _relationships(graph: Graph, vocab: Vocabulary, node: Node, add) -> None:
    types = [t for t in (vocab.type_name(x) for x in node.types) if t]
    page_like = any(vocab.is_a(t, "WebPage") for t in types)
    where = "/".join(types) or None
    if page_like and "mainEntity" in node.data:
        for v in as_list(node.data["mainEntity"]):
            if any(vocab.is_a(t, "WebSite") for t in _target_types(graph, vocab, v)):
                add(rule_id="graph.main_entity_is_website", category=F.WARNING, type=where, property="mainEntity", entity_id=node.id or node.raw_id,
                    title="mainEntity of a page points at the WebSite", message="WebPage.mainEntity refers to the WebSite", explanation="mainEntity names the thing the page is primarily about. The site as a whole "
                    "is not that; it is what the page is part of (isPartOf).", recommendation="Use isPartOf for the WebSite, and point mainEntity at the page's own subject (or leave it out).",
                    doc=F.schema_doc("mainEntity"), evidence={"mainEntity": snippet(v)}, confidence="high")
    if "mainEntityOfPage" in node.data and types:
        for v in as_list(node.data["mainEntityOfPage"]):
            target = v if isinstance(v, str) else (v.get("@id") or v.get("url")) if isinstance(v, dict) else None
            if isinstance(target, str) and target.startswith(("http://", "https://")) and graph.is_local(target) and not _same_page(target, graph.url):
                add(rule_id="graph.main_entity_of_page_elsewhere", category=F.WARNING, type=where, property="mainEntityOfPage", entity_id=node.id or node.raw_id,
                    title="mainEntityOfPage names a different page of the site", message=f"mainEntityOfPage is {target}, but this page is {graph.url}",
                    explanation="mainEntityOfPage says which page the entity is the main subject of. Pointing at another page makes this page's markup describe an entity whose main page is elsewhere.",
                    recommendation="Point it at this page's address, or remove it if the entity is only mentioned here.", doc=F.schema_doc("mainEntityOfPage"), evidence={"mainEntityOfPage": snippet(v)}, confidence="medium")
    if "sameAs" in node.data and types:
        own = {x for x in (node.id, node.data.get("url") if isinstance(node.data.get("url"), str) else None) if x}
        for v in as_list(node.data["sameAs"]):
            if isinstance(v, str) and not v.startswith(("http://", "https://")):
                add(rule_id="graph.same_as_not_url", category=F.WARNING, type=where, property="sameAs", entity_id=node.id or node.raw_id,
                    title="sameAs holds something that is not a web address", message=f"sameAs value '{snippet(v, 60)}' is not a full URL", explanation="sameAs lists the addresses of other pages that identify the same entity: a profile, a Wikidata item, a registry entry.",
                    recommendation="Use the full https:// address of the profile or item.", doc=F.schema_doc("sameAs"), evidence={"sameAs": snippet(v)}, confidence="high")
            elif isinstance(v, str) and any(_same_page(v, o) for o in own if o.startswith("http")):
                add(rule_id="graph.same_as_self", category=F.INFORMATIONAL, type=where, property="sameAs", entity_id=node.id or node.raw_id,
                    title="sameAs repeats the entity's own address", message=f"sameAs lists {v}, which is the entity's own address", explanation="An entity is trivially the same as itself, so the value adds nothing.",
                    recommendation="Keep sameAs for other addresses that identify the entity.", doc=F.schema_doc("sameAs"), evidence={"sameAs": snippet(v)}, confidence="high")
