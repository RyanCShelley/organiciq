"""Expected JSON-LD schema per page_type.

The detector flags pages missing the expected types. We track two levels:

- ``required``: a type that's a hard expectation for this page type (its
  absence is a high-severity gap).
- ``recommended``: a type that strengthens the page's GEO/SEO posture but
  isn't strictly required.

BreadcrumbList is intentionally excluded from every list per project policy.
"""

from __future__ import annotations

# Per-page-type expectations. Keys match page_type values produced by
# topic_hub.page_type. "generic" is the catch-all fallback.
EXPECTED_SCHEMA: dict[str, dict[str, list[str]]] = {
    "editorial": {
        "required": ["Article"],
        "recommended": ["Person", "Organization", "WebPage"],
        "accepts": ["BlogPosting", "NewsArticle"],
    },
    "documentation": {
        "required": ["TechArticle"],
        "recommended": ["HowTo", "Organization", "WebPage"],
        "accepts": ["Article"],
    },
    "faq": {
        "required": ["FAQPage"],
        "recommended": ["Organization", "WebPage"],
        "accepts": [],
    },
    "product": {
        "required": ["Product", "Offer"],
        "recommended": ["AggregateRating", "Review", "Organization"],
        "accepts": ["IndividualProduct", "ProductGroup", "ProductModel"],
    },
    "service": {
        "required": ["Service"],
        "recommended": ["Organization", "WebPage"],
        "accepts": ["ProfessionalService", "LocalBusiness"],
    },
    "productized_service": {
        "required": ["Service", "Offer"],
        "recommended": ["Organization", "WebPage", "AggregateRating"],
        "accepts": ["ProfessionalService", "Product"],
    },
    "category": {
        "required": ["CollectionPage"],
        "recommended": ["WebPage", "Organization"],
        "accepts": ["ItemList"],
    },
    "landing": {
        # WebPage is never required (fine to have, not essential). Organization
        # is the real expectation on a landing page — AI engines need to know
        # who's selling the thing being landed on.
        "required": ["Organization"],
        "recommended": ["WebPage", "Service"],
        "accepts": ["LocalBusiness", "ProfessionalService"],
    },
    "homepage": {
        "required": ["Organization", "WebSite"],
        "recommended": ["WebPage"],
        "accepts": ["LocalBusiness", "ProfessionalService", "Corporation"],
    },
    "about": {
        "required": ["AboutPage"],
        "recommended": ["Organization", "Person"],
        "accepts": ["WebPage"],
    },
    "contact": {
        "required": ["ContactPage"],
        "recommended": ["Organization", "LocalBusiness"],
        "accepts": ["WebPage"],
    },
    "generic": {
        # Catch-all fallback — we don't know what this page is, so we don't
        # require anything specific. WebPage is fine to have but not essential.
        "required": [],
        "recommended": ["WebPage", "Organization"],
        "accepts": [],
    },
}


def expected_for(page_type: str | None) -> dict[str, list[str]]:
    """Look up expected schema for a page type, falling back to generic."""
    if not page_type or page_type not in EXPECTED_SCHEMA:
        return EXPECTED_SCHEMA["generic"]
    return EXPECTED_SCHEMA[page_type]


def find_missing_required(
    page_type: str | None, present_types: list[str]
) -> list[str]:
    """Return required schema types not present on the page.

    A required type counts as satisfied when ANY of its accepted aliases is
    present (e.g. BlogPosting satisfies the editorial Article requirement).
    """
    spec = expected_for(page_type)
    present_set = {t for t in present_types}
    missing: list[str] = []

    required = spec.get("required", [])
    accepts = set(spec.get("accepts", []))

    for req in required:
        # Either the exact required type, OR one of its accepts list, OR an
        # explicitly listed accept that also satisfies the requirement.
        if req in present_set:
            continue
        if any(a in present_set for a in accepts):
            # An accepted alias is present — only counts if it's a natural
            # substitute for THIS specific required entry. We treat any
            # accepted alias as satisfying any required entry in the list
            # because the lists are kept small and curated.
            continue
        missing.append(req)
    return missing


def find_missing_recommended(
    page_type: str | None, present_types: list[str]
) -> list[str]:
    """Return recommended schema types not present on the page."""
    spec = expected_for(page_type)
    present_set = {t for t in present_types}
    return [t for t in spec.get("recommended", []) if t not in present_set]
