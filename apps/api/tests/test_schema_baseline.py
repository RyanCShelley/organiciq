"""The SMA schema baseline layer: what it asks for, what it leaves alone, and that nothing in it is an error."""

from __future__ import annotations

import pytest

from app.schema_validation import findings as F
from app.schema_validation.engine import validate_page
from app.services import schema_audit

CTX = "https://schema.org"
HOME = "https://site.example/"
POST = "https://site.example/blog/post"
ORG = "https://site.example/#organization"
SITE = "https://site.example/#website"


def run(blocks, url=POST, page_type=None):
    return validate_page(url, blocks if isinstance(blocks, list) else [blocks], page_type=page_type)


def base(findings, rule=None):
    return [f for f in findings if f.layer == "baseline" and (rule is None or f.rule_id == f"baseline.{rule}")]


def graph(*nodes):
    return {"@context": CTX, "@graph": list(nodes)}


def linked(name="SEO"):
    return {"@type": "Thing", "name": name, "sameAs": [f"https://www.wikidata.org/wiki/Q1", "https://en.wikipedia.org/wiki/SEO"]}


def full_post():
    return graph(
        {"@type": "Organization", "@id": ORG, "name": "Co"},
        {"@type": "WebSite", "@id": SITE, "name": "Co", "url": HOME, "publisher": {"@id": ORG}},
        {"@type": "Person", "@id": "https://site.example/#a", "name": "A", "url": "https://site.example/a", "jobTitle": "Editor", "worksFor": {"@id": ORG}, "sameAs": ["https://www.linkedin.com/in/a"]},
        {"@type": "WebPage", "@id": POST + "#page", "url": POST, "isPartOf": {"@id": SITE}, "about": [linked()]},
        {"@type": "BlogPosting", "headline": "H", "author": {"@id": "https://site.example/#a"}, "publisher": {"@id": ORG}, "about": [linked()], "mainEntityOfPage": {"@id": POST + "#page"}},
    )


def test_a_page_that_meets_the_baseline_has_no_baseline_finding():
    assert base(run(full_post(), page_type="editorial")) == []


def test_nothing_in_the_baseline_is_an_error():
    out = run(graph({"@type": "Article", "headline": "H"}, {"@type": "WebPage", "name": "P"}), page_type="editorial")
    assert base(out) and all(f.category in (F.ENHANCEMENT, F.INFORMATIONAL) for f in base(out))


def test_a_webpage_must_say_which_website_it_is_part_of():
    out = run(graph({"@type": "WebPage", "name": "P"}))
    assert [f.property for f in base(out, "webpage_is_part_of")] == ["isPartOf"]


def test_a_content_page_with_no_about_is_told_and_a_home_page_is_not():
    page = {"@type": "WebPage", "name": "P", "isPartOf": {"@id": SITE}}
    assert base(run(graph(page), page_type="service"), "about_missing")
    assert not base(run(graph(page), url=HOME, page_type="homepage"), "about_missing")


def test_about_and_mentions_need_both_a_wikidata_item_and_a_wikipedia_page():
    only_wd = {"@type": "Thing", "name": "SEO", "sameAs": ["https://www.wikidata.org/wiki/Q1"]}
    neither = {"@type": "Thing", "name": "Content"}
    out = run(graph({"@type": "WebPage", "isPartOf": {"@id": SITE}, "about": [only_wd], "mentions": [neither]}), page_type="editorial")
    got = {(f.rule_id, f.property, f.evidence["name"]) for f in base(out) if f.rule_id.startswith("baseline.entity_link")}
    assert got == {("baseline.entity_link_wikipedia", "about", "SEO"), ("baseline.entity_link_wikidata", "mentions", "Content"), ("baseline.entity_link_wikipedia", "mentions", "Content")}


def test_about_that_is_only_text_is_not_an_entity():
    out = run(graph({"@type": "WebPage", "isPartOf": {"@id": SITE}, "about": "seo"}), page_type="editorial")
    assert base(out, "about_not_entity")


def test_a_reference_to_a_glossary_term_on_the_page_is_the_internal_link_the_baseline_asks_for():
    term = {"@type": "DefinedTerm", "@id": "https://site.example/glossary#seo", "name": "SEO", "description": "d", "inDefinedTermSet": {"@id": "https://site.example/glossary"},
            "sameAs": ["https://www.wikidata.org/wiki/Q1", "https://en.wikipedia.org/wiki/SEO"]}
    out = run(graph(term, {"@type": "WebPage", "isPartOf": {"@id": SITE}, "about": [{"@id": term["@id"]}]}), page_type="editorial")
    assert not base(out, "entity_link_wikidata") and not base(out, "entity_link_wikipedia")


def test_a_reference_to_something_not_on_the_page_cannot_be_judged():
    out = run(graph({"@type": "WebPage", "isPartOf": {"@id": SITE}, "about": [{"@id": "https://site.example/elsewhere#x"}]}), page_type="editorial")
    assert not [f for f in base(out) if f.rule_id.startswith("baseline.entity_link")]


@pytest.mark.parametrize("author, rule", [(None, "article_author"), ("Jane", "article_author_person"), ({"@type": "Organization", "name": "Co"}, "article_author_person")])
def test_an_article_needs_a_person_as_its_author(author, rule):
    art = {"@type": "BlogPosting", "headline": "H", "publisher": {"@id": ORG}}
    if author:
        art["author"] = author
    assert base(run(graph({"@type": "Organization", "@id": ORG, "name": "Co"}, art), page_type="editorial"), rule)


def test_an_article_needs_its_publisher_to_be_an_organization():
    out = run(graph({"@type": "BlogPosting", "headline": "H", "author": {"@type": "Person", "name": "A"}}), page_type="editorial")
    assert base(out, "article_publisher")


def test_a_website_names_its_publisher_and_a_search_action_is_noted_as_retired_not_wrong():
    out = run(graph({"@type": "WebSite", "name": "Co", "url": HOME, "potentialAction": {"@type": "SearchAction", "target": HOME + "?s={q}", "query-input": "required name=q"}}), url=HOME, page_type="homepage")
    assert base(out, "website_publisher")
    retired = base(out, "search_action_retired")
    assert retired and retired[0].category == F.INFORMATIONAL


def test_the_organization_on_the_home_page_is_asked_for_the_facts_that_identify_it_and_other_pages_are_not():
    org = {"@type": "Organization", "name": "Co", "url": HOME, "logo": HOME + "l.png"}
    home = base(run(graph(org), url=HOME, page_type="homepage"))
    assert {f.property for f in home if f.rule_id == "baseline.org_property"} == {"legalName", "description", "sameAs", "contactPoint", "address", "foundingDate", "founder", "knowsAbout"}
    assert base(run(graph(org), url=HOME, page_type="homepage"), "org_id")
    assert not base(run(graph(org), page_type="editorial"), "org_property")


def test_a_term_belongs_to_a_set_and_a_set_lists_its_terms():
    out = run(graph({"@type": "DefinedTermSet", "name": "Glossary"}, {"@type": "DefinedTerm", "name": "SEO"}), url="https://site.example/glossary", page_type="generic")
    assert {f.rule_id for f in base(out)} >= {"baseline.termset_terms", "baseline.term_property"}


def test_a_service_says_what_it_offers_by_whom_and_where():
    out = run(graph({"@type": "Service", "name": "S"}), url="https://site.example/services/seo", page_type="service")
    assert {f.property for f in base(out, "service_property")} == {"provider", "serviceType", "areaServed"}


def test_breadcrumb_markup_is_a_reminder_to_check_it_is_visible_not_a_fault():
    out = run(graph({"@type": "BreadcrumbList", "itemListElement": []}))
    b = base(out, "breadcrumb_visible")
    assert b and b[0].category == F.INFORMATIONAL and b[0].confidence == "low"


def test_faq_and_howto_are_kept_for_their_structure_not_dropped():
    out = run(graph({"@type": "FAQPage", "mainEntity": []}, {"@type": "HowTo", "name": "h"}))
    notes = [f for f in out if f.rule_id in ("google.faq.restricted", "google.howto.deprecated")]
    assert notes and all(f.category == F.INFORMATIONAL and "baseline keeps this markup for its structure" in f.recommendation for f in notes)


def test_features_google_retired_are_informational_and_say_where_the_row_came_from():
    out = run(graph({"@type": "Course", "name": "C"}))
    c = [f for f in out if f.rule_id == "google.course.deprecated"]
    assert c and c[0].category == F.INFORMATIONAL and "SMA schema baseline" in c[0].explanation


def test_a_business_marking_up_its_own_reviews_is_told_they_earn_no_stars():
    out = run(graph({"@type": "LocalBusiness", "name": "Co", "aggregateRating": {"@type": "AggregateRating", "ratingValue": "5", "reviewCount": "3"}}), url=HOME)
    s = [f for f in out if f.rule_id == "google.self_serving_review"]
    assert s and s[0].category == F.INFORMATIONAL
    assert not [f for f in run(graph({"@type": "Product", "name": "P", "aggregateRating": {"@type": "AggregateRating", "ratingValue": "5", "reviewCount": "3"}})) if f.rule_id == "google.self_serving_review"]


def test_a_site_with_no_glossary_is_told_once_on_its_home_page_and_one_with_a_glossary_is_not():
    blocks = {HOME: [graph({"@type": "WebPage", "name": "H"})], POST: [graph({"@type": "WebPage", "name": "P"})]}
    vocab = schema_audit.load_vocabulary()
    got = schema_audit._glossary_finding(blocks, [POST, HOME], vocab)
    assert [(f.rule_id, f.url) for f in got] == [("baseline.glossary_missing", HOME)]
    blocks[POST] = [graph({"@type": "DefinedTermSet", "name": "G"})]
    assert schema_audit._glossary_finding(blocks, [POST, HOME], vocab) == []
