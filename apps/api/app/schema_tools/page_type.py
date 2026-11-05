"""Page-type detection — classifies each page so the right profile applies.

Detection is a layered process:
 1. URL pattern prior (cheap, deterministic)
 2. Schema.org @type override (more reliable when present)
 3. Productized-service hybrid recognition (Product + Service signals co-occur)

The output drives `page_profiles.evaluate()` — which blockers apply, what the
composite score weighs, which recommendations show. Misclassification is
recoverable via the analyst override in the UI.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Literal

PageType = Literal[
    "editorial",
    "product",
    "service",
    "productized_service",
    "category",
    "landing",
    "faq",
    "homepage",
    "about",
    "documentation",
    "generic",
]

# ---------------------------------------------------------------------------
# URL pattern priors
# ---------------------------------------------------------------------------

# Order matters: more specific patterns first so /products/categories/ doesn't
# match /category/ before /product/.
_URL_PATTERNS: tuple[tuple[PageType, tuple[str, ...]], ...] = (
    ("editorial", (
        "/blog/", "/blogs/", "/post/", "/posts/", "/article/", "/articles/",
        "/news/", "/insights/", "/resources/article/", "/journal/", "/stories/",
        "/perspectives/", "/learn/", "/insights/",
    )),
    ("product", (
        "/product/", "/products/", "/shop/", "/store/", "/item/", "/items/",
        "/buy/", "/p/", "/collections/",
    )),
    ("service", (
        "/services/", "/service/", "/what-we-do/", "/expertise/",
        "/practice-areas/", "/practice-area/", "/solutions/", "/solution/",
        "/offerings/", "/offering/", "/capabilities/", "/capability/",
        "/programs/", "/program/", "/treatments/", "/treatment/",
        "/specialties/", "/specialty/", "/industries/", "/industry/",
    )),
    ("category", (
        "/category/", "/categories/", "/collection/", "/tag/", "/tags/",
        "/topics/", "/topic/", "/archive/",
    )),
    ("faq", ("/faq/", "/faqs/", "/questions/", "/help-center/", "/q-and-a/")),
    ("landing", (
        "/pricing/", "/demo/", "/trial/", "/signup/", "/sign-up/",
        "/get-started/", "/quote/", "/get-a-quote/", "/free-quote/",
    )),
    ("about", (
        "/about/", "/about-us/", "/team/", "/our-team/", "/careers/",
        "/jobs/", "/our-story/", "/who-we-are/", "/leadership/", "/contact/",
        "/contact-us/",
    )),
    ("documentation", (
        "/docs/", "/documentation/", "/api/", "/reference/", "/guides/",
        "/guide/", "/help/", "/support/", "/knowledge-base/", "/kb/",
        "/tutorial/", "/tutorials/", "/how-to/",
    )),
)


def _url_prior(url: str) -> PageType | None:
    """Match URL path against the pattern table. Returns None if no match."""
    try:
        path = (urllib.parse.urlparse(url).path or "").lower()
    except ValueError:
        return None
    if not path or path == "/":
        return "homepage"
    # Ensure leading + trailing slash for predictable contains-matching.
    p = path if path.endswith("/") else path + "/"
    for page_type, patterns in _URL_PATTERNS:
        if any(pat in p for pat in patterns):
            return page_type
    return None


# ---------------------------------------------------------------------------
# Schema.org @type → PageType mapping
# ---------------------------------------------------------------------------

_EDITORIAL_SCHEMAS = frozenset({
    "Article", "NewsArticle", "BlogPosting", "Report", "ScholarlyArticle",
})
_PRODUCT_SCHEMAS = frozenset({
    "Product", "IndividualProduct", "ProductGroup", "ProductModel", "Vehicle",
})
_GENERIC_SERVICE_SCHEMAS = frozenset({
    "Service", "ProfessionalService", "Course", "MedicalProcedure", "TaxiService",
})
# What a page offers, as against who it belongs to. A ProfessionalService or a LocalBusiness is how a site describes its own business, and is repeated on
# every page (the publisher of a blog post, the organization in the footer), so on its own it says nothing about what this page is.
_OFFERING_SCHEMAS = frozenset({"Service", "Course", "MedicalProcedure", "TaxiService"})
_FAQ_SCHEMAS = frozenset({"FAQPage", "QAPage"})
_HOWTO_SCHEMAS = frozenset({"HowTo", "Recipe"})
_CATEGORY_SCHEMAS = frozenset({"CollectionPage", "ItemList"})
_ABOUT_SCHEMAS = frozenset({"AboutPage", "ContactPage", "Person"})

# The 70+ LocalBusiness subtypes — keeping the most common. Pages whose schema
# is just "LocalBusiness" (no subtype) also match.
_LOCAL_BUSINESS_SCHEMAS = frozenset({
    "LocalBusiness",
    # Health / beauty
    "BeautySalon", "DaySpa", "HairSalon", "HealthClub", "NailSalon",
    "MedicalBusiness", "Dentist", "MedicalClinic", "Pharmacy", "Physician",
    "Optician", "PhysicalTherapy", "DiagnosticLab", "VeterinaryCare",
    # Home / construction
    "HomeAndConstructionBusiness", "Electrician", "GeneralContractor",
    "HVACBusiness", "HousePainter", "Locksmith", "MovingCompany",
    "Plumber", "RoofingContractor",
    # Auto
    "AutomotiveBusiness", "AutoBodyShop", "AutoDealer", "AutoRental",
    "AutoRepair", "GasStation", "MotorcycleRepair",
    # Food
    "FoodEstablishment", "Bakery", "BarOrPub", "Brewery", "CafeOrCoffeeShop",
    "FastFoodRestaurant", "Restaurant", "Winery", "Distillery",
    # Legal / financial / professional
    "LegalService", "Attorney", "Notary", "FinancialService",
    "AccountingService", "InsuranceAgency", "BankOrCreditUnion",
    # Lodging / travel
    "LodgingBusiness", "Hotel", "BedAndBreakfast", "Hostel", "Motel",
    "Resort", "TravelAgency",
    # Retail / store
    "Store", "BikeStore", "BookStore", "ClothingStore", "ComputerStore",
    "ElectronicsStore", "FurnitureStore", "GardenStore", "GroceryStore",
    "HardwareStore", "HobbyShop", "HomeGoodsStore", "JewelryStore",
    "LiquorStore", "MensClothingStore", "MobilePhoneStore",
    "MovieRentalStore", "MusicStore", "OfficeEquipmentStore", "OutletStore",
    "PawnShop", "PetStore", "ShoeStore", "SportingGoodsStore", "TireShop",
    "ToyStore", "WholesaleStore",
    # Other commonly-seen
    "RealEstateAgent", "ShoppingCenter", "SportsActivityLocation",
    "ChildCare", "EmploymentAgency", "DryCleaningOrLaundry",
})

# Heuristic: schema names ending in these suffixes are almost always
# LocalBusiness subtypes. Catches the long tail without enumerating all 70+.
_LOCAL_BUSINESS_SUFFIXES = ("Store", "Shop", "Salon", "Spa", "Clinic", "Restaurant")


def _is_local_business(schema_types: set[str]) -> bool:
    if schema_types & _LOCAL_BUSINESS_SCHEMAS:
        return True
    return any(
        t.endswith(_LOCAL_BUSINESS_SUFFIXES) for t in schema_types
    )


def _schema_override(schema_types: list[str]) -> PageType | None:
    """Map JSON-LD @types to a page type. Hybrid detection comes first.

    Returns None when no schema is present, so the URL prior takes over.
    """
    if not schema_types:
        return None
    types = set(schema_types)

    has_product = bool(types & _PRODUCT_SCHEMAS)
    has_service = bool(types & _GENERIC_SERVICE_SCHEMAS) or _is_local_business(types)
    has_offer = "Offer" in types or "AggregateOffer" in types
    has_local = _is_local_business(types)

    # An article on a page is what the page is, whoever publishes it: the business markup beside it is the site's own, not this page's subject.
    if types & _EDITORIAL_SCHEMAS and not (types & _OFFERING_SCHEMAS) and not has_product:
        return "editorial"

    # Productized service: Product + Service co-marked, OR LocalBusiness with
    # an Offer that points to a Service (we can't see the link without parsing
    # makesOffer, but Offer + Service on the same page is the same idea).
    if (has_product and has_service) or (has_local and has_offer and has_service):
        return "productized_service"

    if has_product:
        return "product"
    if has_service:
        return "service"
    if types & _EDITORIAL_SCHEMAS:
        return "editorial"
    if types & _FAQ_SCHEMAS:
        return "faq"
    if types & _HOWTO_SCHEMAS:
        return "documentation"
    if types & _CATEGORY_SCHEMAS:
        return "category"
    if types & _ABOUT_SCHEMAS:
        return "about"
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Question-form titles strongly suggest editorial intent on a generic URL.
_QUESTION_TITLE_RE = re.compile(
    r"^\s*(what|how|why|when|where|who|which)\b", re.IGNORECASE,
)


def detect_page_type(
    url: str,
    schema_types: list[str] | None = None,
    title: str | None = None,
    is_question_url: bool = False,
) -> PageType:
    """Classify a page into one of the supported types.

    Layered resolution:
      1. URL homepage detection (path = "/")
      2. Schema.org @type — most reliable when present
      3. URL pattern prior — fast fallback
      4. Question-shaped title/URL → editorial guess
      5. Generic — caught by everything else

    Args:
        url: Absolute page URL.
        schema_types: JSON-LD @type values extracted by trust_audit. Optional.
        title: Page <title> for question-intent fallback. Optional.
        is_question_url: Cached question-URL flag from trust_audit. Optional.
    """
    schema_types = schema_types or []
    url_guess = _url_prior(url)

    # Homepage detection is URL-driven; schema rarely overrides this in practice
    # (Organization-only schema doesn't make a /pricing/ page a homepage).
    if url_guess == "homepage":
        # An Article on the root URL is unusual but possible; respect schema.
        schema_guess = _schema_override(schema_types)
        if schema_guess in {"editorial", "product", "service", "productized_service"}:
            return schema_guess
        return "homepage"

    schema_guess = _schema_override(schema_types)
    if schema_guess in ("service", "productized_service") and url_guess not in (None, "service", "productized_service"):
        # Only the site's own business is marked up (no Service, Course or Product on the page): the address says more than a business node repeated everywhere.
        if not (set(schema_types) & (_OFFERING_SCHEMAS | _PRODUCT_SCHEMAS)):
            return url_guess
    if schema_guess is not None:
        return schema_guess

    if url_guess is not None:
        return url_guess

    # Last fallback: a question-shaped title is a strong editorial signal even
    # when URL + schema are both ambiguous.
    if is_question_url or (title and _QUESTION_TITLE_RE.match(title)):
        return "editorial"

    return "generic"


# ---------------------------------------------------------------------------
# Evidence-URL detection — service / productized_service profiles count
# internal outbound links to URLs that look like case studies, testimonials,
# portfolio, or client-results pages.
# ---------------------------------------------------------------------------

_EVIDENCE_PATTERNS = (
    "/case-study/", "/case-studies/", "/casestudy/", "/case_studies/",
    "/testimonial/", "/testimonials/", "/reviews/", "/review/",
    "/portfolio/", "/portfolio-item/", "/portfolios/",
    "/work/", "/our-work/", "/works/",
    "/projects/", "/project/",
    "/clients/", "/client-stories/", "/client/",
    "/results/", "/success-stories/", "/success/", "/outcomes/",
    "/showcase/", "/spotlight/",
)


def is_evidence_url(url: str) -> bool:
    """Heuristic: does this URL look like a case study / testimonial / portfolio page?

    Used by the service + productized_service profiles to count "internal
    evidence" links — the analog of external citations for editorial pages.
    """
    try:
        path = (urllib.parse.urlparse(url).path or "").lower()
    except ValueError:
        return False
    if not path:
        return False
    p = path if path.endswith("/") else path + "/"
    return any(pat in p for pat in _EVIDENCE_PATTERNS)
