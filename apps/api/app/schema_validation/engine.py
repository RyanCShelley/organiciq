"""The schema validator: one entry point over four independent layers.

    from app.schema_validation.engine import validate_page
    findings = validate_page(url, blocks, page_type="service", site_ids=...)

The layers do not depend on each other and can be changed, or one switched off, on their own:

1. `schemaorg_rules`: is the markup valid Schema.org (types, properties, domains through inheritance, ranges, deprecation)?
2. `graph_rules`: do the entities hold together (references, duplicate and conflicting definitions, relationships)?
3. `google_rules`: does the markup meet what a Google Search feature needs? (never an error)
4. `baseline_rules`: SMA's own schema standard, the structured knowledge layer every client gets (never an error)
5. `recommendation_rules`: contextual suggestions for this kind of page (never an error)
"""

from __future__ import annotations

from typing import Any

from app.schema_validation import findings as F
from app.schema_validation import baseline_rules, google_rules, graph_rules, recommendation_rules, schemaorg_rules
from app.schema_validation import graph as graph_mod
from app.schema_validation.vocabulary import Vocabulary, load

#: `about` and `mentions` are defined on CreativeWork, so when a Service carries one the fix is usually a CreativeWork that is on the page.
_CREATIVE_WORK_ONLY = {"about", "mentions"}


def _contextualize(g: graph_mod.Graph, vocab: Vocabulary, findings: list[F.Finding]) -> None:
    pages = [n for n in g.nodes if n.top_level and any(vocab.is_a(vocab.type_name(t) or "", "CreativeWork") for t in n.types)]
    for f in findings:
        if f.rule_id == "schemaorg.property_domain" and f.property in _CREATIVE_WORK_ONLY and pages:
            where = "/".join(pages[0].types)
            f.recommendation = (f"The page's {where} node ({pages[0].id or 'no @id'}) is a CreativeWork, where '{f.property}' is defined. If this value says what the page is {'about' if f.property == 'about' else 'mentioning'}, "
                                f"it belongs there; if it describes the {f.type}, use a property {f.type} supports (for a Service: serviceType, category or areaServed). Check the meaning before moving it.")
            f.confidence = "high"


def _dedupe(findings: list[F.Finding]) -> list[F.Finding]:
    seen: set[tuple[Any, ...]] = set()
    out: list[F.Finding] = []
    for f in findings:
        key = (f.rule_id, f.entity_id, f.type, f.property, str(f.evidence), f.message)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def validate_page(url: str, blocks: list[Any], *, page_type: str | None = None, site_ids: dict[str, int] | None = None, vocab: Vocabulary | None = None) -> list[F.Finding]:
    vocab = vocab or load()
    g = graph_mod.build(url, blocks)
    findings = [
        *schemaorg_rules.check(g, vocab),
        *graph_rules.check(g, vocab, site_ids=site_ids),
        *google_rules.check(g, vocab),
        *baseline_rules.check(g, vocab, page_type),
        *recommendation_rules.main_entity(g, vocab, page_type),
    ]
    _contextualize(g, vocab, findings)
    findings = _dedupe(findings)
    findings.sort(key=lambda f: (F.RANK[f.category], f.layer, f.rule_id, f.entity_id or ""))
    return findings


def defined_ids(url: str, blocks: list[Any]) -> set[str]:
    """The identifiers a page defines, for the site-wide registry the audit builds so a reference to an entity another page defines can be told from one nothing defines."""
    return set(graph_mod.build(url, blocks).index)
