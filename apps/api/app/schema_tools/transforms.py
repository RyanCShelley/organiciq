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
    pages = find_nodes_by_type(graph, "WebPage", "ServicePage")
    services = find_nodes_by_type(graph, "Service", "ProfessionalService", "FinancialService")

    if not pages or not services:
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

# Valid properties per schema.org type — covers the types we generate or
# commonly encounter. Includes inherited properties from parent types.
# Breadcrumb / BreadcrumbList intentionally excluded from validation tables.
_VALID_PROPERTIES: dict[str, set[str]] = {
    "Organization": {
        "name", "url", "logo", "description", "sameAs", "address", "telephone",
        "email", "foundingDate", "founder", "numberOfEmployees", "areaServed",
        "image", "identifier", "alternateName", "contactPoint", "member",
        "department", "subOrganization", "parentOrganization", "brand",
        "award", "knowsAbout", "slogan", "legalName", "taxID",
    },
    "LocalBusiness": {
        "name", "url", "logo", "description", "sameAs", "address", "telephone",
        "email", "foundingDate", "areaServed", "image", "identifier",
        "alternateName", "contactPoint", "parentOrganization", "brand",
        "openingHours", "openingHoursSpecification", "priceRange", "geo",
        "review", "aggregateRating", "hasOfferCatalog", "paymentAccepted",
        "currenciesAccepted", "menu", "servesCuisine",
    },
    "ProfessionalService": {
        "name", "url", "logo", "description", "sameAs", "address", "telephone",
        "email", "foundingDate", "areaServed", "image", "identifier",
        "alternateName", "contactPoint", "parentOrganization", "brand",
        "openingHours", "openingHoursSpecification", "priceRange", "geo",
        "review", "aggregateRating", "hasOfferCatalog", "serviceType",
        "knowsAbout", "slogan",
    },
    "Service": {
        "name", "url", "description", "sameAs", "image", "identifier",
        "provider", "serviceType", "areaServed", "offers", "hasOfferCatalog",
        "category", "serviceOutput", "serviceArea", "availableChannel",
        "termsOfService", "aggregateRating", "review", "brand",
        "alternateName",
    },
    "WebSite": {
        "name", "url", "description", "publisher", "potentialAction",
        "sameAs", "alternateName", "inLanguage",
    },
    "WebPage": {
        "name", "url", "description", "isPartOf", "mainEntity", "about",
        "primaryImageOfPage", "datePublished", "dateModified",
        "author", "inLanguage", "potentialAction", "sameAs", "significantLink",
        "speakable", "relatedLink", "lastReviewed", "reviewedBy",
        # NOTE: 'breadcrumb' deliberately omitted — we don't recommend
        # BreadcrumbList per project policy.
    },
    "Article": {
        "name", "url", "description", "headline", "author", "datePublished",
        "dateModified", "image", "publisher", "mainEntityOfPage", "about",
        "inLanguage", "articleBody", "articleSection", "keywords",
        "wordCount", "alternativeHeadline",
    },
    "BlogPosting": {
        "name", "url", "description", "headline", "author", "datePublished",
        "dateModified", "image", "publisher", "mainEntityOfPage", "about",
        "inLanguage", "articleBody", "articleSection", "keywords",
        "wordCount", "alternativeHeadline",
    },
    "NewsArticle": {
        "name", "url", "description", "headline", "author", "datePublished",
        "dateModified", "image", "publisher", "mainEntityOfPage", "about",
        "inLanguage", "articleBody", "articleSection", "keywords",
        "wordCount", "alternativeHeadline", "dateline",
    },
    "Product": {
        "name", "url", "description", "image", "sku", "mpn", "gtin", "gtin8",
        "gtin13", "gtin14", "brand", "manufacturer", "model", "color",
        "category", "offers", "aggregateRating", "review", "weight",
        "height", "width", "depth", "material", "isAccessoryOrSparePartFor",
        "isRelatedTo", "isSimilarTo",
    },
    "Offer": {
        "price", "priceCurrency", "availability", "url", "validFrom",
        "validThrough", "priceValidUntil", "itemCondition", "seller",
        "shippingDetails", "hasMerchantReturnPolicy", "category",
    },
    "FAQPage": {
        "name", "url", "description", "mainEntity", "inLanguage",
        "isPartOf", "about", "author", "datePublished", "dateModified",
    },
    "Question": {
        "name", "text", "acceptedAnswer", "answerCount", "upvoteCount",
        "dateCreated", "author",
    },
    "Answer": {
        "text", "upvoteCount", "dateCreated", "author",
    },
    "HowTo": {
        "name", "url", "description", "image", "step", "totalTime",
        "estimatedCost", "supply", "tool", "yield", "performTime",
        "prepTime", "datePublished", "dateModified", "author",
    },
    "ImageObject": {
        "url", "contentUrl", "width", "height", "caption", "description",
        "name", "encodingFormat", "thumbnail",
    },
    "Person": {
        "name", "url", "image", "description", "sameAs", "jobTitle",
        "worksFor", "alumniOf", "knowsAbout", "hasCredential", "award",
        "telephone", "email", "address", "givenName", "familyName",
    },
    "Thing": {
        "name", "url", "description", "sameAs", "identifier", "image",
        "alternateName",
    },
}

# ORGANICIQ: the table above was written for markup the Topic Hub tool *generates*, so it lists only the properties that tool uses.
# Audited here, it would call valid markup invalid (dateCreated on an Article, gtin12 on a Product). These are the other common
# schema.org properties of each type, so only real mistakes (a misspelt `productId`, a property from the wrong type) are flagged.
_ARTICLE_MORE = {
    "dateCreated", "creator", "contributor", "thumbnailUrl", "copyrightHolder", "copyrightYear", "isAccessibleForFree", "license",
    "text", "abstract", "genre", "audience", "isPartOf", "hasPart", "commentCount", "comment", "video", "aggregateRating", "review",
    "citation", "mentions", "speakable", "educationalLevel", "timeRequired", "position", "publishingPrinciples", "locationCreated",
    "sourceOrganization", "sameAs", "identifier", "potentialAction", "subjectOf", "alternateName", "editor", "translator", "isBasedOn",
}
_PRODUCT_MORE = {
    "gtin12", "productID", "hasVariant", "isVariantOf", "audience", "award", "countryOfOrigin", "inProductGroupWithID", "itemCondition",
    "logo", "pattern", "size", "slogan", "sameAs", "additionalProperty", "alternateName", "releaseDate", "potentialAction", "subjectOf",
    "mainEntityOfPage", "identifier", "hasMerchantReturnPolicy", "positiveNotes", "negativeNotes", "asin", "nsn", "purchaseDate",
    "keywords", "disambiguatingDescription", "funding", "hasEnergyConsumptionDetails", "isConsumableFor", "manufacturer", "width",
}
_OFFER_MORE = {
    "offeredBy", "gtin", "gtin8", "gtin12", "gtin13", "gtin14", "eligibleRegion", "inventoryLevel", "itemOffered", "priceSpecification",
    "warranty", "sku", "mpn", "availabilityStarts", "availabilityEnds", "areaServed", "acceptedPaymentMethod", "deliveryLeadTime",
    "name", "description", "image", "identifier", "businessFunction", "eligibleQuantity", "ineligibleRegion", "mainEntityOfPage",
    "aggregateRating", "review", "leaseLength", "includesObject", "advanceBookingRequirement",
}
for _name in ("Article", "BlogPosting", "NewsArticle"):
    _VALID_PROPERTIES[_name] |= _ARTICLE_MORE
_VALID_PROPERTIES["Product"] |= _PRODUCT_MORE
_VALID_PROPERTIES["Offer"] |= _OFFER_MORE

# Property names we'll auto-replace or strip. None means "delete it."
_PROPERTY_FIXES: dict[str, dict[str, str | None]] = {
    "Organization": {"provider": None},
    "LocalBusiness": {"provider": None},
    "ProfessionalService": {"provider": None},
    # about on Service is already removed by fix_about_placement, but we
    # double-flag any that slip through the per-property validator.
    "Service": {"about": None},
}

_META_KEYS = frozenset({"@context", "@type", "@id", "@graph", "@vocab", "@reverse", "@language"})


def validate_properties(
    graph: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Strip properties that aren't valid on the node's schema.org @type."""
    corrections: list[dict[str, str]] = []
    for node in graph:
        node_type = node.get("@type", "")
        types = [node_type] if isinstance(node_type, str) else list(node_type)

        valid: set[str] = set(_META_KEYS)
        matched_type = False
        for t in types:
            if t in _VALID_PROPERTIES:
                valid |= _VALID_PROPERTIES[t]
                matched_type = True

        if not matched_type:
            continue

        # Apply named fixes first (move/rename specific known-bad properties).
        for t in types:
            if t in _PROPERTY_FIXES:
                for bad_prop, replacement in _PROPERTY_FIXES[t].items():
                    if bad_prop in node:
                        val = node.pop(bad_prop)
                        if replacement and replacement not in node:
                            node[replacement] = val
                            detail = (
                                f"Replaced invalid '{bad_prop}' with '{replacement}' on {t}"
                            )
                        else:
                            detail = f"Removed invalid '{bad_prop}' from {t}"
                        corrections.append(
                            {
                                "transform": "validate_properties",
                                "node_id": node.get("@id", "?"),
                                "detail": detail,
                            }
                        )

        # Strip any remaining property not in the valid set.
        invalid_keys = [k for k in node if k not in valid]
        for k in invalid_keys:
            node.pop(k)
            corrections.append(
                {
                    "transform": "validate_properties",
                    "node_id": node.get("@id", "?"),
                    "detail": (
                        f"Removed invalid property '{k}' from {'/'.join(types)} "
                        "(not in schema.org spec)"
                    ),
                }
            )

    return graph, corrections


# ---------------------------------------------------------------------------
# Transform 6: validate @id references
# ---------------------------------------------------------------------------


def validate_id_refs(
    graph: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Flag @id references that don't resolve to any node in the graph.

    Pure detection — the bad reference is left in place. Callers may surface
    the warning so the analyst can fix the source.
    """
    corrections: list[dict[str, str]] = []
    defined_ids = {node.get("@id") for node in graph if node.get("@id")}

    def check_refs(obj: object, parent_path: str = "") -> None:
        if isinstance(obj, dict):
            if list(obj.keys()) == ["@id"] and obj["@id"] not in defined_ids:
                corrections.append(
                    {
                        "transform": "validate_id_refs",
                        "node_id": parent_path,
                        "detail": f"Dangling @id reference: {obj['@id']} (at {parent_path})",
                    }
                )
            for k, v in obj.items():
                check_refs(v, f"{parent_path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                check_refs(v, f"{parent_path}[{i}]")

    for node in graph:
        check_refs(node, node.get("@id", "root"))

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
