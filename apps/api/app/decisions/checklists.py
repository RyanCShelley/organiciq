"""Dedicated page-type checklists for service, location, category, and homepage pages.

Each checklist item inspects parsed crawl or live page facts (`schema_types`, `faq_questions`,
`conversion_elements`, `sections`, `h1`, `title`, `description`, `word_count`, etc.) so
already-satisfied checks report `"done"` and missing or unverified checks report `"needed"` or `"check"`.
Items are ordered by active `ClientFocus` (`visibility`, `traffic`, `leads`) when supplied.
"""

from __future__ import annotations

from typing import Any

from app.decisions import action_context as ac

CHECKLIST_PAGE_TYPES = frozenset({ac.SERVICE, ac.LOCATION, ac.CATEGORY, ac.HOMEPAGE})

_FOCUS_PRIORITY: dict[str, tuple[str, ...]] = {
    "leads": ("conversion", "navigation", "ctr", "content", "schema"),
    "traffic": ("ctr", "content", "navigation", "conversion", "schema"),
    "visibility": ("content", "schema", "navigation", "ctr", "conversion"),
}
_STATUS_ORDER = {"needed": 0, "check": 1, "done": 2}


def _extract_facts(facts: Any | None) -> dict[str, Any] | None:
    """Normalize either a dict (`page_facts` / `outline`) or a `ParsedPage` into a plain dict."""
    if facts is None:
        return None
    if isinstance(facts, dict):
        outline = facts.get("outline") if isinstance(facts.get("outline"), dict) else {}
        sections = facts.get("sections") or outline.get("sections") or []
        schema_types = facts.get("schema_types") or outline.get("schema_types") or []
        faq_questions = facts.get("faq_list") or outline.get("faq_list") or facts.get("faq_questions")
        if isinstance(faq_questions, int):
            faq_count = faq_questions
            faq_questions = []
        else:
            faq_questions = list(faq_questions or [])
            faq_count = len(faq_questions)
        return {
            "title": facts.get("title") or outline.get("title") or "",
            "description": facts.get("description") or "",
            "h1": facts.get("h1") or outline.get("h1") or "",
            "word_count": int(facts.get("word_count") or outline.get("word_count") or 0),
            "sections": list(sections),
            "schema_types": [str(s) for s in schema_types if s],
            "has_faq": bool(facts.get("has_faq") or facts.get("has_faq_section") or facts.get("has_faq_schema") or faq_count > 0),
            "faq_count": faq_count,
            "conversion_elements": facts.get("conversion_elements") if facts.get("conversion_elements") is not None else outline.get("conversion_elements"),
            "contact_only_in_footer": facts.get("contact_only_in_footer"),
        }
    # ParsedPage or PageFacts-like object
    sections = list(getattr(facts, "sections", None) or [])
    schema_blocks = getattr(facts, "schema_blocks", None) or []
    schema_types = sorted({b.schema_type for b in schema_blocks if getattr(b, "schema_type", None)})
    faq_qs = list(getattr(facts, "faq_questions", None) or [])
    return {
        "title": getattr(facts, "title", None) or "",
        "description": getattr(facts, "description", None) or "",
        "h1": getattr(facts, "h1", None) or "",
        "word_count": int(getattr(facts, "word_count", 0) or 0),
        "sections": [
            {
                "heading": getattr(s, "heading", "") if not isinstance(s, dict) else s.get("heading", ""),
                "has_table": getattr(s, "has_table", False) if not isinstance(s, dict) else bool(s.get("has_table")),
                "has_list": getattr(s, "has_list", False) if not isinstance(s, dict) else bool(s.get("has_list")),
                "has_stat": getattr(s, "has_stat", False) if not isinstance(s, dict) else bool(s.get("has_stat")),
            }
            for s in sections
        ],
        "schema_types": schema_types,
        "has_faq": bool(getattr(facts, "has_faq_section", False) or getattr(facts, "has_faq_schema", False) or faq_qs),
        "faq_count": len(faq_qs),
        "conversion_elements": getattr(facts, "conversion_elements", None),
        "contact_only_in_footer": getattr(facts, "contact_only_in_footer", None),
    }


def _has_schema(norm: dict[str, Any], candidates: tuple[str, ...]) -> bool:
    present = {s.lower() for s in norm["schema_types"]}
    return any(c.lower() in present for c in candidates)


def _has_heading_keyword(norm: dict[str, Any], keywords: tuple[str, ...]) -> bool:
    for s in norm["sections"]:
        h = (s.get("heading") if isinstance(s, dict) else getattr(s, "heading", "")) or ""
        low = h.lower()
        if any(kw in low for kw in keywords):
            return True
    return False


def _has_structured_section(norm: dict[str, Any]) -> bool:
    for s in norm["sections"]:
        if isinstance(s, dict):
            if s.get("has_table") or s.get("has_list") or s.get("has_stat"):
                return True
        elif getattr(s, "has_table", False) or getattr(s, "has_list", False) or getattr(s, "has_stat", False):
            return True
    return False


def _item(
    id_: str,
    title: str,
    why: str,
    steps: list[str],
    action_type: str,
    benefit: str,
    status: str,
    category: str,
) -> dict[str, Any]:
    return {
        "id": id_,
        "title": title,
        "why": why,
        "steps": steps,
        "action_type": action_type,
        "benefit": benefit,
        "status": status,
        "category": category,
    }


def _service_checklist(norm: dict[str, Any] | None) -> list[dict[str, Any]]:
    def st(cond: bool | None, *, fallback: str = "check") -> str:
        if norm is None or cond is None:
            return fallback
        return "done" if cond else "needed"

    conv_ok = None
    if norm is not None and norm["conversion_elements"] is not None:
        conv_ok = norm["conversion_elements"] > 0 and not bool(norm["contact_only_in_footer"])

    opening_ok = None if norm is None else ("check" if (norm["h1"] and norm["word_count"] >= 150) else "needed")
    process_ok = (
        "check"
        if norm is None
        else "done"
        if (_has_structured_section(norm) or _has_heading_keyword(norm, ("process", "how it works", "pricing", "cost", "deliverable", "step", "timeline")))
        else ("check" if len(norm["sections"]) >= 2 else "needed")
    )
    proof_ok = (
        "done"
        if norm is not None and (_has_schema(norm, ("Review", "AggregateRating")) or _has_heading_keyword(norm, ("review", "testimonial", "case stud", "result", "client", "accreditation", "award")))
        else "check"
    )
    schema_ok = st(_has_schema(norm, ("Service", "ProfessionalService", "FinancialService", "LegalService", "MedicalBusiness", "LocalBusiness")) if norm else None)
    faq_ok = st((norm["has_faq"] or norm["faq_count"] >= 2) if norm else None)

    return [
        _item(
            "CHK-SVC-1",
            "State what the service is, who it is for, and where it is offered in the opening",
            "Buyers landing on a service page decide in seconds whether the scope fits them.",
            ["Confirm the main heading and first paragraph name the service, target buyer, and service area or delivery model."],
            "Optimize existing page",
            "SEO and conversion",
            opening_ok or "check",
            "content",
        ),
        _item(
            "CHK-SVC-2",
            "Place a visible enquiry or booking CTA above the fold and outside the footer",
            "If the only way to get in touch sits in the footer, interested visitors leave before acting.",
            ["Put a clear form, phone/email link, or booking CTA in the upper section and after key proof blocks."],
            "Improve conversion path",
            "Conversion",
            st(conv_ok),
            "conversion",
        ),
        _item(
            "CHK-SVC-3",
            "Detail deliverables, process steps, or pricing expectations",
            "Specifics on scope, timeline, and how pricing works qualify leads and reduce hesitation.",
            ["Add a concise bulleted list or step breakdown showing what is included and what happens after an enquiry."],
            "Optimize existing page",
            "Conversion",
            process_ok,
            "content",
        ),
        _item(
            "CHK-SVC-4",
            "Show proof beside the service claim (reviews, case studies, accreditations)",
            "Independent proof near the CTA turns sceptical shoppers into enquiries.",
            ["Place client testimonials, quantified outcomes, or industry credentials next to the main CTA."],
            "Optimize existing page",
            "Conversion",
            proof_ok,
            "conversion",
        ),
        _item(
            "CHK-SVC-5",
            "Add Service structured data matching the visible service details",
            "Service schema clarifies the offering, provider, and service area for search engines.",
            ["Validate or add JSON-LD Service markup reflecting the page's visible service name and areaServed."],
            "Update structured data",
            "SEO",
            schema_ok,
            "schema",
        ),
        _item(
            "CHK-SVC-6",
            "Answer common buyer objections in a service FAQ",
            "FAQs resolve scope, cost, and turnaround questions while capturing long-tail and AI queries.",
            ["Add 3–5 real buyer questions about scope, timeline, and pricing with direct 1–3 sentence answers."],
            "Optimize existing page",
            "SEO and AI visibility",
            faq_ok,
            "content",
        ),
    ]


def _location_checklist(norm: dict[str, Any] | None) -> list[dict[str, Any]]:
    def st(cond: bool | None, *, fallback: str = "check") -> str:
        if norm is None or cond is None:
            return fallback
        return "done" if cond else "needed"

    nap_status = "check"
    if norm is not None:
        nap_status = "needed" if (norm["contact_only_in_footer"] or norm["word_count"] < 100) else "check"

    cta_ok = None
    if norm is not None and norm["conversion_elements"] is not None:
        cta_ok = norm["conversion_elements"] > 0 and not bool(norm["contact_only_in_footer"])

    local_schema = (
        "LocalBusiness", "Dentist", "MedicalBusiness", "LegalService", "FinancialService",
        "HomeAndConstructionBusiness", "Plumber", "Electrician", "HVACBusiness",
        "AutoRepair", "Restaurant", "Store", "ProfessionalService",
    )
    schema_ok = st(_has_schema(norm, local_schema) if norm else None)
    services_ok = (
        "check"
        if norm is None
        else ("check" if len(norm["sections"]) >= 2 and (_has_structured_section(norm) or _has_heading_keyword(norm, ("service", "area", "serve", "offer"))) else "needed")
    )
    proof_ok = (
        "done"
        if norm is not None and (_has_schema(norm, ("Review", "AggregateRating")) or _has_heading_keyword(norm, ("review", "hours", "direction", "map", "parking", "testimonial")))
        else "check"
    )
    meta_status = "check" if norm is None else ("check" if (norm["title"] and norm["description"]) else "needed")

    return [
        _item(
            "CHK-LOC-1",
            "Display full local NAP (name, address, phone) and service areas in body text",
            "Local searchers and search engines look for explicit city/neighbourhood names and contact info in the page body.",
            ["Ensure street address, local phone number, opening hours, and neighbourhoods/cities served appear in body copy, not only the footer."],
            "Optimize existing page",
            "Local SEO",
            nap_status,
            "content",
        ),
        _item(
            "CHK-LOC-2",
            "Offer an immediate click-to-call or local booking CTA",
            "Local intent is urgent: visitors want to call, get directions, or book right away.",
            ["Place a tap-to-call button or short local booking form near the top of the page."],
            "Improve conversion path",
            "Conversion",
            st(cta_ok),
            "conversion",
        ),
        _item(
            "CHK-LOC-3",
            "Include LocalBusiness structured data for this location",
            "LocalBusiness JSON-LD reinforces address, hours, geo coordinates, and areaServed.",
            ["Add or verify LocalBusiness (or a specific subtype) JSON-LD matching the exact visible NAP on this location page."],
            "Update structured data",
            "Local SEO",
            schema_ok,
            "schema",
        ),
        _item(
            "CHK-LOC-4",
            "List services available at this location and link to core service pages",
            "Connecting location pages to core service pages distributes internal authority and guides local buyers.",
            ["Summarize the services offered here with in-content links to each dedicated service page."],
            "Improve internal linking",
            "SEO and conversion",
            services_ok,
            "navigation",
        ),
        _item(
            "CHK-LOC-5",
            "Add local proof: reviews, directions, parking, or hours",
            "Location-specific reviews and practical visit details differentiate the page from generic boilerplate.",
            ["Embed local customer reviews, landmarks/parking guidance, and operating hours."],
            "Optimize existing page",
            "Conversion",
            proof_ok,
            "conversion",
        ),
        _item(
            "CHK-LOC-6",
            "Tailor the title tag and meta description with the city/region",
            "Searchers click results that immediately confirm the business serves their area.",
            ["Include the primary service and city/region naturally in the title tag and meta description."],
            "Optimize existing page",
            "SEO",
            meta_status,
            "ctr",
        ),
    ]


def _category_checklist(norm: dict[str, Any] | None) -> list[dict[str, Any]]:
    def st(cond: bool | None, *, fallback: str = "check") -> str:
        if norm is None or cond is None:
            return fallback
        return "done" if cond else "needed"

    intro_status = "check" if norm is None else ("check" if norm["h1"] else "needed")
    schema_ok = st(_has_schema(norm, ("CollectionPage", "ItemList", "OfferCatalog")) if norm else None)
    compare_ok = st(_has_structured_section(norm) if norm else None)
    meta_status = "check" if norm is None else ("check" if (norm["title"] and norm["description"]) else "needed")

    return [
        _item(
            "CHK-CAT-1",
            "Keep a concise 1–2 sentence category intro above the product grid",
            "A tight intro establishes topical relevance without pushing products below the fold.",
            ["Confirm the H1 and a 1–2 sentence intro explain what the collection covers without displacing the product grid."],
            "Optimize existing page",
            "SEO and conversion",
            intro_status,
            "content",
        ),
        _item(
            "CHK-CAT-2",
            "Show buyer-deciding attributes on product cards (price, spec, rating, availability)",
            "Shoppers comparing options on a category page need key specs upfront before clicking into a product.",
            ["Verify each product card shows name, price, key differentiating spec/size, and stock/rating where applicable."],
            "Optimize existing page",
            "Conversion",
            "check",
            "conversion",
        ),
        _item(
            "CHK-CAT-3",
            "Add CollectionPage / ItemList structured data",
            "CollectionPage and ItemList markup help search engines parse the listed items and hierarchy.",
            ["Verify JSON-LD declares CollectionPage or ItemList reflecting the products listed on this page."],
            "Update structured data",
            "SEO",
            schema_ok,
            "schema",
        ),
        _item(
            "CHK-CAT-4",
            "Provide clear paths to products, filters, and sibling categories",
            "Facet links and related collection links help buyers narrow choices and improve crawlable internal linking.",
            ["Ensure every product card links cleanly and add links to closely related collections or buying guides."],
            "Improve internal linking",
            "SEO and conversion",
            "check",
            "navigation",
        ),
        _item(
            "CHK-CAT-5",
            "Include a brief buying-criteria summary or comparison list",
            "For commercial searches, a compact 'best for' list or comparison table helps buyers pick quickly and wins snippets.",
            ["Add a short bulleted guide or comparison table below the grid explaining how to choose within this range."],
            "Optimize existing page",
            "SEO and AI visibility",
            compare_ok,
            "content",
        ),
        _item(
            "CHK-CAT-6",
            "Align category title and meta description with commercial buyer terms",
            "Category pages win clicks when snippets highlight breadth, key specs, or delivery/trust differentiators.",
            ["Check that title and meta description name the category and give a concrete reason to browse here."],
            "Optimize existing page",
            "SEO",
            meta_status,
            "ctr",
        ),
    ]


def _homepage_checklist(norm: dict[str, Any] | None) -> list[dict[str, Any]]:
    def st(cond: bool | None, *, fallback: str = "check") -> str:
        if norm is None or cond is None:
            return fallback
        return "done" if cond else "needed"

    vp_status = "check" if norm is None else ("check" if (norm["h1"] and norm["word_count"] >= 100) else "needed")
    cta_ok = None
    if norm is not None and norm["conversion_elements"] is not None:
        cta_ok = norm["conversion_elements"] > 0 and not bool(norm["contact_only_in_footer"])
    nav_status = "check" if norm is None else ("check" if len(norm["sections"]) >= 2 else "needed")
    trust_status = (
        "done"
        if norm is not None and (_has_schema(norm, ("Review", "AggregateRating")) or _has_heading_keyword(norm, ("review", "testimonial", "client", "trusted", "partner", "award")))
        else "check"
    )
    schema_ok = st(_has_schema(norm, ("Organization", "LocalBusiness", "Corporation", "WebSite")) if norm else None)
    meta_status = "check" if norm is None else ("check" if (norm["title"] and norm["description"]) else "needed")

    return [
        _item(
            "CHK-HOME-1",
            "State who the business is, what it offers, and who it serves above the fold",
            "The homepage must immediately orient first-time visitors and search engines.",
            ["Review the main hero headline and subheadline to confirm they plainly state what you do and for whom."],
            "Optimize existing page",
            "SEO and conversion",
            vp_status,
            "content",
        ),
        _item(
            "CHK-HOME-2",
            "Feature a primary conversion CTA above the fold",
            "High-intent visitors arriving on the homepage need an obvious next step immediately.",
            ["Keep one primary action button (quote, book, shop) visible on the first screen without scrolling."],
            "Improve conversion path",
            "Conversion",
            st(cta_ok),
            "conversion",
        ),
        _item(
            "CHK-HOME-3",
            "Route visitors clearly to core service, category, and location pages",
            "The homepage is the site's top authority hub and main routing layer.",
            ["Link prominently from homepage sections to your highest-priority money pages with descriptive anchor text."],
            "Improve internal linking",
            "SEO and conversion",
            nav_status,
            "navigation",
        ),
        _item(
            "CHK-HOME-4",
            "Surface trust signals and social proof on the homepage",
            "Reviews, client logos, and credentials build instant confidence for non-brand visitors.",
            ["Display verified customer reviews, case-study highlights, or industry certifications."],
            "Optimize existing page",
            "Conversion",
            trust_status,
            "conversion",
        ),
        _item(
            "CHK-HOME-5",
            "Maintain Organization / LocalBusiness and WebSite structured data",
            "Entity schema connects the brand, logo, social profiles, and site search cleanly.",
            ["Verify Organization or LocalBusiness and WebSite JSON-LD exist on the homepage without errors."],
            "Update structured data",
            "SEO",
            schema_ok,
            "schema",
        ),
        _item(
            "CHK-HOME-6",
            "Keep homepage title and meta description focused on brand + core offering",
            "Homepage snippets appear for brand and broad non-brand searches alike.",
            ["Include the brand name, core category/service, and primary market or value proposition within length limits."],
            "Optimize existing page",
            "SEO",
            meta_status,
            "ctr",
        ),
    ]


_BUILDERS = {
    ac.SERVICE: _service_checklist,
    ac.LOCATION: _location_checklist,
    ac.CATEGORY: _category_checklist,
    ac.HOMEPAGE: _homepage_checklist,
}


def checklist_for(page_type: str, facts: Any | None = None, *, focus: str | None = None) -> list[dict[str, Any]]:
    """Return structured, fact-aware checklist items for `service`, `location`, `category`, or `homepage`.

    Returns `[]` for other page types. When `focus` (`visibility`, `traffic`, `leads`) is given,
    items are sorted by focus relevance first, then by status (`needed` -> `check` -> `done`).
    """
    builder = _BUILDERS.get((page_type or "").strip().lower())
    if builder is None:
        return []
    norm = _extract_facts(facts)
    items = builder(norm)
    norm_focus = (focus or "").strip().lower()
    if norm_focus in _FOCUS_PRIORITY:
        order = _FOCUS_PRIORITY[norm_focus]
        rank = {cat: idx for idx, cat in enumerate(order)}
        items.sort(key=lambda item: (rank.get(item["category"], len(order)), _STATUS_ORDER.get(item["status"], 1)))
    else:
        items.sort(key=lambda item: _STATUS_ORDER.get(item["status"], 1))
    return items
