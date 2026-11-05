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
