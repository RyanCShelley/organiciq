"""Layer 4: contextual recommendations. Nothing here is an error and nothing here is a rule of Schema.org or Google.

These look at what kind of page this is and what the markup already says, and suggest what would make the markup say more. They are
**enhancements** (or informational), and each one only fires when the situation is clear enough that the suggestion is right for this page:

* `mainEntity` is recommended only when the page has a WebPage node, no mainEntity yet, and exactly one node of the family that page kind is about
  (a Service on a service page, a Product on a product page, an Article-family node on an article). Two candidates is ambiguous, so nothing is said.
* A required *kind* of markup (an Article on an article page) is met by any subtype the vocabulary lists below it (BlogPosting, NewsArticle, TechArticle…).
"""

from __future__ import annotations

from typing import Any

from app.schema_validation import findings as F
from app.schema_validation.graph import Graph, Node, as_list
from app.schema_validation.vocabulary import Vocabulary

#: The family of node a page of each kind is about.
SUBJECT_FAMILY = {
    "service": "Service",
    "productized_service": "Service",
    "product": "Product",
    "editorial": "Article",
    "documentation": "Article",
}


def satisfied(vocab: Vocabulary, present: list[str], required: str, accepts: tuple[str, ...] = ()) -> bool:
    """Is the expected type present, as itself, as any subtype the vocabulary lists below it, or as one of the accepted alternatives (and their subtypes)?"""
    wanted = {required, *accepts}
    for name in present:
        t = vocab.type_name(name) or name
        if t in wanted or any(vocab.is_a(t, w) for w in wanted if vocab.has_type(w)):
            return True
    return False


def main_entity(graph: Graph, vocab: Vocabulary, page_type: str | None) -> list[F.Finding]:
    family = SUBJECT_FAMILY.get(page_type or "")
    if not family:
        return []
    pages = [n for n in graph.nodes if n.top_level and any(vocab.is_a(vocab.type_name(t) or "", "WebPage") for t in n.types)]
    if not pages:
        return []
    page = pages[0]
    if page.data.get("mainEntity"):
        return []
    candidates = [n for n in graph.nodes if n.top_level and n is not page and any(vocab.is_a(vocab.type_name(t) or "", family) for t in n.types)]
    if len(candidates) != 1 or not candidates[0].id:
        return []
    c = candidates[0]
    # Already tied the other way round (the entity says it is the page's main entity): nothing to add.
    for v in as_list(c.data.get("mainEntityOfPage")):
        target = v if isinstance(v, str) else (v.get("@id") if isinstance(v, dict) else None)
        if target and (target == graph.url or target == page.id):
            return []
    own = c.data.get("url") if isinstance(c.data.get("url"), str) else None
    sure = bool(own and own.rstrip("/") == graph.url.rstrip("/")) or c.id.split("#")[0].rstrip("/") == graph.url.rstrip("/")
    ctype = "/".join(c.types)
    return [F.Finding(
        url=graph.url, layer="recommendation", rule_id="recommendation.main_entity", category=F.ENHANCEMENT, entity_id=page.id or page.raw_id, type="WebPage", property="mainEntity",
        title=f"Name the page's {family.lower()} as its mainEntity", message=f"The page has a WebPage and one {ctype} ({c.id}), but the WebPage does not say the {ctype} is its main entity",
        explanation="mainEntity tells consumers which entity the page is primarily about. It is a recommendation, not a requirement: the markup is valid without it. "
        f"It is suggested here because this is a {page_type} page with a single {family} node.", recommendation=f'Add "mainEntity": {{"@id": "{c.id}"}} to the WebPage.',
        doc="https://schema.org/mainEntity", evidence={"candidate": c.id, "types": c.types}, auto_fixable=True, confidence="high" if sure else "medium",
    )]


def missing_types(vocab: Vocabulary, page_type: str, present: list[str], spec: dict[str, Any], url: str, ignored: set[str] | None = None) -> list[F.Finding]:
    out: list[F.Finding] = []
    accepts = tuple(spec.get("accepts", ()))
    for kind, label, level in (("required", "expected", "enhancement"), ("recommended", "recommended", "enhancement")):
        for t in spec.get(kind, ()):
            if satisfied(vocab, present, t, accepts if kind == "required" else ()):
                continue
            subtypes = sorted(n for n in (vocab._types if hasattr(vocab, "_types") else {}) if vocab.is_a(n, t) and n != t)[:6]
            out.append(F.Finding(
                url=url, layer="recommendation", rule_id=f"recommendation.missing_type_{kind}", category=F.ENHANCEMENT, type=t,
                title=f"No {t} markup on {page_type.replace('_', ' ')} pages" if kind == "required" else f"No {t} markup on {page_type.replace('_', ' ')} pages (recommended)",
                message=f"The page reads as a {page_type.replace('_', ' ')} page and carries no {t} markup" + (f" (or a subtype such as {', '.join(subtypes)})" if subtypes else ""),
                explanation=f"{t} markup is {label} for this kind of page. Its absence is an opportunity, not a fault: nothing in Schema.org or Google's requirements makes it mandatory.",
                recommendation=f"Add {t} markup if the page is a {t}.", doc=F.schema_doc(t), evidence={"present": present[:10]}, confidence="medium",
            ))
    return out
