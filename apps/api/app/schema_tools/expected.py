"""Expected JSON-LD schema per page_type.

The detector flags pages missing the expected types. We track two levels:

- ``required``: a type that's a hard expectation for this page type (its
  absence is a high-severity gap).
- ``recommended``: a type that strengthens the page's GEO/SEO posture but
  isn't strictly required.

WebPage is expected on every page (the SMA schema baseline: every page is a node in the site's graph, with `isPartOf`), and any subtype satisfies it
(AboutPage, CollectionPage, FAQPage…), so a kind whose own required type is such a subtype does not list it twice. BreadcrumbList is excluded from every list: the baseline adds it only where the site shows a visible trail.
"""

from __future__ import annotations

# Per-page-type expectations. Keys match page_type values produced by
# topic_hub.page_type. "generic" is the catch-all fallback.
EXPECTED_SCHEMA: dict[str, dict[str, list[str]]] = {
    "editorial": {
        "required": ["Article", "WebPage"],
        "recommended": ["Person", "Organization"],
        "accepts": ["BlogPosting", "NewsArticle"],
    },
    "documentation": {
        "required": ["TechArticle", "WebPage"],
        "recommended": ["HowTo", "Organization"],
        "accepts": ["Article"],
    },
    "faq": {
        "required": ["FAQPage"],
        "recommended": ["Organization"],
        "accepts": [],
    },
    "product": {
        "required": ["Product", "Offer", "WebPage"],
        "recommended": ["AggregateRating", "Review", "Organization"],
        "accepts": ["IndividualProduct", "ProductGroup", "ProductModel"],
    },
    "service": {
        "required": ["Service", "WebPage"],
        "recommended": ["Organization"],
        "accepts": ["ProfessionalService", "LocalBusiness"],
    },
    "productized_service": {
        "required": ["Service", "Offer", "WebPage"],
        "recommended": ["Organization", "AggregateRating"],
        "accepts": ["ProfessionalService", "Product"],
    },
    "category": {
        "required": ["CollectionPage"],
        "recommended": ["Organization"],
        "accepts": ["ItemList"],
    },
    "landing": {
        # Organization is the real expectation on a landing page: AI engines
        # need to know who's selling the thing being landed on.
        "required": ["Organization", "WebPage"],
        "recommended": ["Service"],
        "accepts": ["LocalBusiness", "ProfessionalService"],
    },
    "homepage": {
        "required": ["Organization", "WebSite", "WebPage"],
        "recommended": [],
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
        # Catch-all fallback: we don't know what this page is, so only what every
        # page is expected to be (a WebPage in the site's graph) is required.
        "required": ["WebPage"],
        "recommended": ["Organization"],
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

    A required type is met by the type itself, by any subtype the Schema.org vocabulary lists below it (TechArticle, ScholarlyArticle and every other
    kind of Article satisfy "Article"), or by one of the accepted alternatives and their subtypes. This is a recommendation about the markup a page of
    this kind usually carries, not a rule of Schema.org or Google; the audit reports it as an enhancement.
    """
    from app.schema_validation.recommendation_rules import satisfied
    from app.schema_validation.vocabulary import load

    vocab = load()
    spec = expected_for(page_type)
    accepts = tuple(spec.get("accepts", []))
    return [req for req in spec.get("required", []) if not satisfied(vocab, list(present_types), req, accepts)]


def find_missing_recommended(
    page_type: str | None, present_types: list[str]
) -> list[str]:
    """Return recommended schema types not present on the page (a subtype counts as its parent)."""
    from app.schema_validation.recommendation_rules import satisfied
    from app.schema_validation.vocabulary import load

    vocab = load()
    spec = expected_for(page_type)
    return [t for t in spec.get("recommended", []) if not satisfied(vocab, list(present_types), t)]
