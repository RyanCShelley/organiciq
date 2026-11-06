"""Layer 3: does the markup make the page eligible for a Google Search feature?

This layer is independent of Schema.org validity. A property Google does not read is not wrong, and Schema.org-valid markup can still miss what a
feature needs. Nothing here is ever an **error**: Google's requirements decide eligibility for a feature, not whether the markup is valid.

* a property Google *requires* for a feature, missing from a node of that feature's type: **warning** (the page is not eligible for that result);
* a property Google *recommends*: **enhancement**;
* a feature Google no longer shows, or shows only to some sites: **informational**.

The table below is data, one row per feature, each with the Google documentation page it was written from and the month it was last checked against
it. When Google changes a feature, that row changes and nothing else does. The rows were checked against the live documentation pages on `REVIEWED`:
Article, Breadcrumb, Product snippet, Local business, Organization, Video, Event and Review snippet list the required and recommended properties used here,
and the FAQ and How-to pages record the restriction and the removal. Google does not version these pages, so re-check a row against its `doc` before changing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schema_validation import findings as F
from app.schema_validation.graph import Graph, Node, as_list
from app.schema_validation.schemaorg_rules import snippet
from app.schema_validation.vocabulary import Vocabulary

REVIEWED = "2026-11-04"
_BASE = "https://developers.google.com/search/docs/appearance/structured-data/"


_STRUCTURE = ("No change is required. The SMA schema baseline keeps this markup for its structure, not for a result: it breaks the page into pieces a machine can read and quote. "
              "Keep it, and make sure it matches the visible page word for word.")
_BASELINE = "Per the SMA schema baseline (v2, Oct 2026); not re-checked against Google's documentation."


@dataclass(frozen=True)
class Feature:
    key: str
    name: str
    type: str  # the Schema.org type the feature reads, subtypes included
    doc: str
    required: tuple[str, ...] = ()  # "a|b" means one of them
    recommended: tuple[str, ...] = ()
    status: str = "supported"  # supported, restricted, deprecated
    note: str = ""
    exclude: tuple[str, ...] = ()  # subtypes another feature owns
    keep: str = "No change is required. Keep it only if it serves another purpose."  # what to tell a person about markup that earns no result
    source: str = ""  # where the row comes from when it is not Google's own page, so the finding says so


FEATURES: tuple[Feature, ...] = (
    Feature("article", "Article", "Article", _BASE + "article", recommended=("author", "datePublished", "dateModified", "headline", "image")),
    Feature("breadcrumb", "Breadcrumb", "BreadcrumbList", _BASE + "breadcrumb", required=("itemListElement",)),
    Feature("product", "Product snippet", "Product", _BASE + "product-snippet", required=("name", "review|aggregateRating|offers"), recommended=("brand", "image", "description", "sku")),
    Feature("local_business", "Local business", "LocalBusiness", _BASE + "local-business", required=("name", "address"),
            recommended=("telephone", "url", "geo", "openingHoursSpecification", "priceRange")),
    Feature("organization", "Organization", "Organization", _BASE + "organization", recommended=("name", "url", "logo", "address", "telephone", "sameAs"), exclude=("LocalBusiness",)),
    Feature("site_name", "Site name", "WebSite", "https://developers.google.com/search/docs/appearance/site-names", required=("name", "url"), recommended=("alternateName",)),
    Feature("video", "Video", "VideoObject", _BASE + "video", required=("name", "thumbnailUrl", "uploadDate"), recommended=("description", "duration", "contentUrl")),
    Feature("event", "Event", "Event", _BASE + "event", required=("name", "startDate", "location"), recommended=("description", "endDate", "image", "offers", "eventStatus")),
    Feature("review", "Review snippet", "Review", _BASE + "review-snippet", required=("itemReviewed", "reviewRating", "author")),
    Feature("faq", "FAQ", "FAQPage", _BASE + "faqpage", required=("mainEntity",), status="restricted",
            note="Since August 2023 Google shows FAQ rich results only for well-known government and health websites.", keep=_STRUCTURE),
    Feature("howto", "How-to", "HowTo", _BASE + "how-to", status="deprecated", note="Google stopped showing how-to rich results in 2023, so this markup no longer earns a result.", keep=_STRUCTURE),
    # Retired features, from the SMA schema baseline (v2, Oct 2026). Not re-checked against Google's pages here; re-check a row against its `doc` before relying on its date.
    Feature("course", "Course info", "Course", _BASE + "course", status="deprecated", note="Google retired the course info result.", source=_BASELINE),
    Feature("claimreview", "Fact check", "ClaimReview", _BASE + "factcheck", status="deprecated", note="Google retired the fact check result.", source=_BASELINE),
    Feature("dataset", "Dataset", "Dataset", _BASE + "dataset", status="restricted", note="Dataset markup is read only by Google's Dataset Search, not by Google Search.", source=_BASELINE),
    Feature("specialannouncement", "Special announcement", "SpecialAnnouncement", _BASE + "special-announcements", status="deprecated", note="Google retired the special announcement result.", source=_BASELINE),
    Feature("practiceproblem", "Practice problems", "Quiz", _BASE + "practice-problems", status="deprecated", note="Google retired the practice problem result.", source=_BASELINE),
    Feature("vehicle", "Vehicle listing", "Vehicle", _BASE + "vehicle-listing", status="deprecated", note="Google retired the vehicle listing result.", source=_BASELINE),
)


def _present(node: Node, prop: str) -> bool:
    return node.data.get(prop) not in (None, "", [], {})


def _satisfied(node: Node, spec: str) -> bool:
    return any(_present(node, p) for p in spec.split("|"))


def _feature_nodes(vocab: Vocabulary, graph: Graph, feature: Feature) -> list[tuple[Node, str]]:
    """Nodes the feature applies to: of its type (or a subtype), and standing for the page rather than embedded as a detail (an Organization inside an article's `publisher`)."""
    out: list[tuple[Node, str]] = []
    for node in graph.nodes:
        if not (node.top_level or node.parent_property in ("mainEntity", "mainEntityOfPage")):
            continue
        for raw in node.types:
            t = vocab.type_name(raw)
            if t and vocab.is_a(t, feature.type) and not any(vocab.is_a(t, e) for e in feature.exclude):
                out.append((node, t))
                break
    return out


def check(graph: Graph, vocab: Vocabulary) -> list[F.Finding]:
    out: list[F.Finding] = []
    for feature in FEATURES:
        for node, t in _feature_nodes(vocab, graph, feature):
            base = dict(url=graph.url, layer="google", entity_id=node.id or node.raw_id, type=t, doc=feature.doc)
            if feature.status != "supported":
                out.append(F.Finding(rule_id=f"google.{feature.key}.{feature.status}", category=F.INFORMATIONAL, title=f"{feature.name}: {feature.note.split('.')[0]}",
                                     message=f"{t} markup is present. {feature.note}", explanation=feature.note + " The markup is still valid Schema.org, and other consumers may read it." + (f" {feature.source}" if feature.source else ""),
                                     recommendation=feature.keep, evidence={"@type": t}, confidence="high" if not feature.source else "medium", **base))
                if feature.status == "deprecated":
                    continue
            for spec in feature.required:
                if not _satisfied(node, spec):
                    out.append(F.Finding(
                        rule_id="google.missing_required", category=F.WARNING, property=spec, title=f"Google's {feature.name} result needs '{spec}' on {feature.type}",
                        message=f"{t} has no '{spec}', which Google requires for its {feature.name} result", explanation=f"Google lists '{spec}' as required for {feature.name} eligibility. "
                        "The markup is valid Schema.org without it; the page simply cannot earn that result.", recommendation=f"Add '{spec}' to the {t} node if the page should be eligible.",
                        evidence={"@type": t, "present": sorted(k for k in node.data if not k.startswith('@'))[:12]}, confidence="high", **base))
            if feature.status == "restricted":
                continue
            for prop in feature.recommended:
                if not _satisfied(node, prop):
                    out.append(F.Finding(
                        rule_id="google.missing_recommended", category=F.ENHANCEMENT, property=prop, title=f"Google recommends '{prop}' on {feature.type} for its {feature.name} result",
                        message=f"{t} has no '{prop}', which Google recommends for its {feature.name} result", explanation="Recommended properties are not needed for eligibility, but they give Google more to show and to understand.",
                        recommendation=f"Add '{prop}' if the information exists on the page.", evidence={"@type": t}, confidence="high", **base))
    out += _self_serving_reviews(graph, vocab)
    return out


def _self_serving_reviews(graph: Graph, vocab: Vocabulary) -> list[F.Finding]:
    """Reviews of the business itself, in its own Organization or LocalBusiness markup, are not eligible for review snippets (Google's review snippet guidelines)."""
    out: list[F.Finding] = []
    for node in graph.nodes:
        if not node.top_level:
            continue
        types = [t for t in (vocab.type_name(x) for x in node.types) if t]
        if not any(vocab.is_a(t, "Organization") for t in types):
            continue
        for prop in ("aggregateRating", "review"):
            if node.data.get(prop) in (None, "", [], {}):
                continue
            out.append(F.Finding(
                rule_id="google.self_serving_review", layer="google", category=F.INFORMATIONAL, property=prop, url=graph.url, entity_id=node.id or node.raw_id, type="/".join(types),
                title=f"Reviews of the business itself are not eligible for review snippets ('{prop}' on an organization)",
                message=f"'{prop}' is on the {'/'.join(types)} node, which is the business itself",
                explanation="Google does not show review stars for reviews a business writes or collects about itself and marks up on its own Organization or LocalBusiness node. The markup is valid Schema.org.",
                recommendation="No change is required for validity. For stars, mark up genuine reviews of a product or software application on the page that shows them.", doc=_BASE + "review-snippet",
                evidence={prop: snippet(node.data.get(prop), 120)}, confidence="medium"))
    return out
