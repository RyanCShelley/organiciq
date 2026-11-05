"""The schema validator: Schema.org vocabulary rules, graph resolution, Google feature rules and recommendations, as four independent layers.

Each reported false positive has a test that it is gone, and a test beside it that the nearby genuine mistake is still found.
"""

from __future__ import annotations

import pytest

from app.schema_validation import findings as F
from app.schema_validation import google_rules, graph as graph_mod, recommendation_rules
from app.schema_validation.engine import defined_ids, validate_page
from app.schema_validation.vocabulary import load
from app.services import schema_audit

URL = "https://site.example/services/seo/"
HOME = "https://site.example/"
CTX = "https://schema.org"


def run(blocks, url=URL, **kw):
    return validate_page(url, blocks if isinstance(blocks, list) else [blocks], **kw)


def rules(findings, layer=None):
    return [f.rule_id for f in findings if layer is None or f.layer == layer]


def about(findings, prop, rule="schemaorg.property_domain"):
    return [f for f in findings if f.rule_id == rule and f.property == prop]


def node(type_, **props):
    return {"@context": CTX, "@type": type_, **props}


# ── the vocabulary ───────────────────────────────────────────────────────────


def test_the_vocabulary_is_a_versioned_release_and_inheritance_is_walked_through_every_parent():
    v = load()
    assert v.version and v.source.startswith("https://schema.org")
    assert {"Service", "Intangible", "Thing"} <= v.ancestors("Service")
    assert {"ImageObject", "MediaObject", "CreativeWork", "Thing"} <= v.ancestors("ImageObject")
    # Multiple inheritance: a Hospital is a CivicStructure, an EmergencyService and a MedicalOrganization.
    assert {"CivicStructure", "EmergencyService", "MedicalOrganization", "LocalBusiness", "Organization", "Place"} <= v.ancestors("Hospital")


@pytest.mark.parametrize("name", ["Service", "https://schema.org/Service", "http://schema.org/Service", "schema:Service", "https://www.schema.org/Service/"])
def test_a_type_is_recognised_however_it_is_written(name):
    assert load().type_name(name) == "Service"


def test_a_foreign_vocabulary_is_not_a_schema_org_name():
    v = load()
    assert v.type_name("http://xmlns.com/foaf/0.1/Person") is None and v.term("foaf:Person") == (None, True)


# ── the ten reported warnings ────────────────────────────────────────────────


@pytest.mark.parametrize("type_", ["Organization", "ProfessionalService", "Service", "Person", "Product"])
def test_disambiguatingDescription_is_valid_on_every_thing(type_):
    assert not about(run(node(type_, name="X", disambiguatingDescription="short")), "disambiguatingDescription")


def test_inLanguage_is_valid_on_an_ImageObject_through_MediaObject_and_CreativeWork():
    assert not about(run(node("ImageObject", url="https://site.example/a.png", inLanguage="en-US")), "inLanguage")
    # ...and still wrong on something that is not a CreativeWork, Event or the other types it is defined on.
    assert about(run(node("Organization", name="X", inLanguage="en-US")), "inLanguage")


def test_isRelatedTo_is_defined_on_Service_and_is_not_defined_on_an_Organization():
    assert not about(run(node("Service", name="S", isRelatedTo={"@type": "Service", "name": "T"})), "isRelatedTo")
    assert about(run(node("Organization", name="X", isRelatedTo={"@type": "Service", "name": "T"})), "isRelatedTo")


@pytest.mark.parametrize("type_", ["Thing", "Service", "Organization", "WebPage", "Article"])
def test_mainEntityOfPage_is_defined_on_Thing_so_every_type_accepts_it(type_):
    assert not about(run(node(type_, name="X", mainEntityOfPage=URL)), "mainEntityOfPage")


def test_audience_is_defined_on_Service_and_not_on_an_Organization():
    assert not about(run(node("Service", name="S", audience={"@type": "Audience", "audienceType": "Dentists"})), "audience")
    assert about(run(node("Organization", name="X", audience={"@type": "Audience", "audienceType": "Dentists"})), "audience")


@pytest.mark.parametrize("prop", ["about", "mentions"])
def test_about_and_mentions_are_defined_on_CreativeWork_so_they_are_a_real_mismatch_on_a_Service(prop):
    found = about(run(node("Service", name="S", **{prop: {"@type": "Thing", "name": "SEO"}})), prop)
    assert found and found[0].category == F.WARNING and found[0].layer == "schemaorg", "a domain mismatch is a warning: Schema.org's domains are expected types, not hard limits"
    assert "CreativeWork" in found[0].message
    assert not about(run(node("WebPage", name="P", **{prop: {"@type": "Thing", "name": "SEO"}})), prop)
    assert not about(run(node("Article", headline="H", **{prop: {"@type": "Thing", "name": "SEO"}})), prop)


def test_about_on_a_service_points_to_the_pages_creative_work_in_the_recommendation():
    graph = {"@context": CTX, "@graph": [{"@type": "WebPage", "@id": URL + "#webpage", "url": URL}, {"@type": "Service", "@id": URL + "#service", "about": {"@type": "Thing", "name": "SEO"}}]}
    [f] = about(run(graph), "about")
    assert "WebPage" in f.recommendation and "serviceType" in f.recommendation and f.auto_fixable is False, "never moved automatically: its meaning has to be checked"


# ── multiple inheritance and multiple types ──────────────────────────────────


def test_a_property_from_any_parent_of_a_multiply_inheriting_type_is_valid():
    # isAcceptingNewPatients is defined on MedicalOrganization, which Hospital inherits from.
    assert not about(run(node("Hospital", name="H", isAcceptingNewPatients=True)), "isAcceptingNewPatients")


def test_a_node_with_several_types_may_use_what_any_of_them_allows():
    # serviceType is a Service property; the node is also an Organization.
    assert not about(run(node(["Organization", "Service"], name="X", serviceType="SEO")), "serviceType")
    assert about(run(node(["Organization", "Person"], name="X", serviceType="SEO")), "serviceType")


def test_a_custom_type_is_not_judged_and_does_not_hide_the_valid_types_beside_it():
    out = run(node(["Service", "acme:Thing"], name="S", about={"@type": "Thing", "name": "x"}))
    assert about(out, "about"), "the Service half is still checked"
    out = run(node("acme:Gadget", name="G", anything="goes"))
    assert not [f for f in out if f.layer == "schemaorg" and f.category in (F.ERROR, F.WARNING)], "a foreign type is outside Schema.org, so nothing is judged against it"


# ── names and values ─────────────────────────────────────────────────────────


def test_a_property_that_does_not_exist_is_an_error_and_a_case_slip_names_the_right_spelling():
    [bad] = about(run(node("Organization", name="X", fooBarBaz="1")), "fooBarBaz", "schemaorg.unknown_property")
    assert bad.category == F.ERROR and bad.layer == "schemaorg"
    [case] = about(run(node("Organization", Name="X")), "Name", "schemaorg.property_case")
    assert case.category == F.ERROR and "'name'" in case.title and case.auto_fixable


def test_a_type_written_in_the_wrong_case_is_an_error_and_an_unknown_type_is_a_warning():
    [case] = [f for f in run(node("service", name="S")) if f.rule_id == "schemaorg.type_case"]
    assert case.category == F.ERROR and "'Service'" in case.title
    [unknown] = [f for f in run(node("Servicepagexyz", name="S")) if f.rule_id == "schemaorg.unknown_type"]
    assert unknown.category == F.WARNING and unknown.confidence == "medium"


def test_prefixed_properties_from_another_vocabulary_are_not_judged():
    assert not [f for f in run(node("Organization", name="X", **{"og:title": "T", "dct:title": "T"})) if f.layer == "schemaorg"]


@pytest.mark.parametrize("value,ok", [("2026-10-31", True), ("2026-10-31T09:30:00Z", True), ("2026-10-31T09:30:00+02:00", True), ("yesterday", False), ("31/10/2026", False)])
def test_a_date_must_be_iso_8601(value, ok):
    found = about(run(node("Article", headline="H", datePublished=value)), "datePublished", "schemaorg.property_range")
    assert bool(found) is (not ok)


def test_a_node_of_the_wrong_type_for_a_property_is_a_warning_and_the_right_type_is_not():
    assert about(run(node("Article", headline="H", author={"@type": "Product", "name": "P"})), "author", "schemaorg.property_range")
    assert not about(run(node("Article", headline="H", author={"@type": "Person", "name": "P"})), "author", "schemaorg.property_range")
    assert not about(run(node("Article", headline="H", author={"@type": "Organization", "name": "O"})), "author", "schemaorg.property_range")
    assert about(run(node("Organization", name={"@type": "Organization", "name": "O"})), "name", "schemaorg.property_range"), "a node where plain text is expected"


def test_numbers_and_booleans_where_text_is_accepted_are_not_flagged():
    assert not about(run(node("LocalBusiness", name="B", telephone=5551234, postalCode=12345)), "telephone", "schemaorg.property_range")


def test_deprecated_vocabulary_is_informational_not_an_error():
    [dep] = [f for f in run(node("Movie", name="M", actors=[{"@type": "Person", "name": "A"}])) if f.rule_id == "schemaorg.deprecated_property"]
    assert dep.category == F.INFORMATIONAL and "actor" in dep.recommendation


# ── the graph ────────────────────────────────────────────────────────────────


def test_an_id_defined_in_another_block_resolves_and_is_not_dangling():
    blocks = [
        {"@context": CTX, "@type": "Organization", "@id": "https://site.example/#organization", "name": "X"},
        {"@context": CTX, "@type": "WebSite", "@id": "https://site.example/#website", "name": "X", "url": "https://site.example/", "publisher": {"@id": "https://site.example/#organization"}},
    ]
    assert "graph.dangling_reference" not in rules(run(blocks, url=HOME))


def test_relative_and_fragment_identifiers_resolve_against_the_page_address():
    blocks = [
        {"@context": CTX, "@graph": [
            {"@type": "Organization", "@id": "#organization", "name": "X"},
            {"@type": "WebPage", "@id": "/services/seo/#webpage", "url": URL, "publisher": {"@id": "https://site.example/services/seo/#organization"}, "isPartOf": {"@id": "#organization"}},
        ]},
    ]
    assert "graph.dangling_reference" not in rules(run(blocks))


def test_a_node_defined_inside_another_node_counts_as_defined():
    blocks = [{"@context": CTX, "@type": "Article", "headline": "H", "publisher": {"@type": "Organization", "@id": "https://site.example/#organization", "name": "X"},
               "author": {"@id": "https://site.example/#organization"}}]
    assert "graph.dangling_reference" not in rules(run(blocks))


def test_a_reference_to_a_schema_org_term_is_a_vocabulary_value_not_an_entity():
    out = run(node("Product", name="P", offers={"@type": "Offer", "price": "5", "priceCurrency": "USD", "availability": {"@id": "https://schema.org/InStock"}}))
    assert not [f for f in out if f.rule_id.startswith("graph.") and "InStock" in f.message]


def test_an_external_reference_is_informational_and_is_not_an_error():
    out = run(node("Organization", name="X", sameAs=["https://www.wikidata.org/wiki/Q1"], parentOrganization={"@id": "https://partner.example/#org"}))
    [ext] = [f for f in out if f.rule_id == "graph.external_reference"]
    assert ext.category == F.INFORMATIONAL and ext.property == "parentOrganization"
    assert not [f for f in out if f.rule_id == "graph.dangling_reference"]


def test_a_local_reference_nothing_defines_is_a_warning_with_the_property_it_is_on():
    out = run(node("Article", headline="H", publisher={"@id": "https://site.example/#nobody"}), site_ids={})
    [d] = [f for f in out if f.rule_id == "graph.dangling_reference"]
    assert d.category == F.WARNING and d.property == "publisher" and d.confidence == "high" and "nowhere on the crawled site" in d.message


def test_a_local_reference_another_page_defines_is_informational_when_the_site_was_checked():
    ref = {"@id": "https://site.example/#organization"}
    out = run(node("Article", headline="H", publisher=ref), site_ids={"https://site.example/#organization": 40})
    [f] = [f for f in out if f.rule_id.startswith("graph.") and f.property == "publisher"]
    assert f.rule_id == "graph.defined_elsewhere" and f.category == F.INFORMATIONAL and "40 other page" in f.message
    # With no site registry the page cannot tell, so it warns at medium confidence rather than claiming nothing defines it.
    [g] = [f for f in run(node("Article", headline="H", publisher=ref)) if f.rule_id == "graph.dangling_reference"]
    assert g.confidence == "medium"


def test_a_site_wide_registry_marks_the_ids_each_page_defines():
    assert defined_ids(HOME, [node("Organization", **{"@id": "https://site.example/#organization", "name": "X"})]) == {"https://site.example/#organization"}


def test_the_same_id_defined_twice_with_different_values_is_a_conflict_and_with_the_same_values_is_a_note():
    org = "https://site.example/#organization"
    conflict = run([{"@context": CTX, "@graph": [{"@type": "Organization", "@id": org, "name": "Acme", "telephone": "1"}, {"@type": "Organization", "@id": org, "name": "Acme Inc", "telephone": "1"}]}], url=HOME)
    [c] = [f for f in conflict if f.rule_id == "graph.conflicting_definitions"]
    assert c.category == F.WARNING and "name" in c.message and "telephone" not in c.message
    same = run([{"@context": CTX, "@graph": [{"@type": "Organization", "@id": org, "name": "Acme"}, {"@type": "Organization", "@id": org, "name": "Acme"}]}], url=HOME)
    assert [f.category for f in same if f.rule_id == "graph.duplicate_definition"] == [F.INFORMATIONAL]
    # Definitions that only add to one another merge cleanly: nothing to report beyond the repetition.
    merged = run([{"@context": CTX, "@graph": [{"@type": "Organization", "@id": org, "name": "Acme"}, {"@type": "Organization", "@id": org, "telephone": "1"}]}], url=HOME)
    assert "graph.conflicting_definitions" not in rules(merged)


def test_a_cycle_of_references_is_legal_and_does_not_loop():
    blocks = [{"@context": CTX, "@graph": [{"@type": "Organization", "@id": "#a", "name": "A", "subOrganization": {"@id": "#b"}}, {"@type": "Organization", "@id": "#b", "name": "B", "parentOrganization": {"@id": "#a"}}]}]
    assert "graph.dangling_reference" not in rules(run(blocks))


def test_blank_nodes_and_untyped_values_do_not_break_the_walk():
    blocks = [{"@context": CTX, "@type": "Organization", "name": {"@value": "X", "@language": "en"}, "address": {"@id": "_:addr"}, "@graph": None}]
    run(blocks)  # no exception
    assert any(f.rule_id == "graph.dangling_reference" for f in run([{"@context": CTX, "@type": "Organization", "name": "X", "address": {"@id": "_:addr"}}]))


def test_malformed_blocks_are_skipped_and_the_valid_ones_are_still_read():
    out = run(["not an object", 42, None, node("Organization", name="X", fooBarBaz="y")])
    assert [f for f in out if f.rule_id == "schemaorg.unknown_property"], "the valid block was still validated"
    assert "graph.not_a_node" in rules(out)


def test_a_block_without_a_context_is_an_error_and_a_remote_context_is_a_warning():
    [none] = [f for f in run([{"@type": "Organization", "name": "X"}]) if f.rule_id == "graph.missing_context"]
    assert none.category == F.ERROR and none.auto_fixable
    [remote] = [f for f in run([{"@context": "https://example.org/context.jsonld", "@type": "Organization", "name": "X"}]) if f.rule_id == "graph.remote_context"]
    assert remote.category == F.WARNING
    assert "graph.remote_context" not in rules(run([{"@context": ["https://schema.org", {"acme": "https://acme.example/"}], "@type": "Organization", "name": "X"}]))


def test_mainEntity_pointing_at_the_website_is_a_warning_and_pointing_at_the_subject_is_not():
    site = {"@type": "WebSite", "@id": HOME + "#website", "name": "X", "url": HOME}
    bad = {"@context": CTX, "@graph": [site, {"@type": "WebPage", "@id": URL + "#webpage", "mainEntity": {"@id": HOME + "#website"}}]}
    assert "graph.main_entity_is_website" in rules(run(bad))
    good = {"@context": CTX, "@graph": [{"@type": "Service", "@id": URL + "#service", "name": "S"}, {"@type": "WebPage", "@id": URL + "#webpage", "mainEntity": {"@id": URL + "#service"}}]}
    assert "graph.main_entity_is_website" not in rules(run(good))


def test_mainEntityOfPage_naming_another_page_of_the_site_is_a_warning_and_this_page_is_not():
    assert "graph.main_entity_of_page_elsewhere" in rules(run(node("Article", headline="H", mainEntityOfPage="https://site.example/other/")))
    assert "graph.main_entity_of_page_elsewhere" not in rules(run(node("Article", headline="H", mainEntityOfPage=URL)))
    assert "graph.main_entity_of_page_elsewhere" not in rules(run(node("Article", headline="H", mainEntityOfPage={"@type": "WebPage", "@id": URL})))


def test_sameAs_must_be_addresses_and_repeating_the_entitys_own_address_is_only_a_note():
    bad = [f for f in run(node("Organization", name="X", sameAs=["linkedin.com/company/x", "https://www.facebook.com/x"])) if f.rule_id == "graph.same_as_not_url"]
    assert len(bad) == 1 and bad[0].category == F.WARNING
    own = [f for f in run(node("Organization", **{"@id": HOME + "#o"}, name="X", url=HOME, sameAs=[HOME])) if f.rule_id == "graph.same_as_self"]
    assert own and own[0].category == F.INFORMATIONAL


# ── Google, independent of Schema.org validity ───────────────────────────────


def test_a_property_google_does_not_use_is_not_an_error():
    out = run(node("Article", headline="H", author={"@type": "Person", "name": "A"}, disambiguatingDescription="x", alternativeHeadline="y"))
    assert not [f for f in out if f.category in (F.ERROR, F.WARNING)], "valid Schema.org that Google ignores is not wrong"


def test_google_requirements_are_warnings_in_the_google_layer_and_never_errors():
    out = run(node("Product", name="P"))
    [req] = [f for f in out if f.rule_id == "google.missing_required"]
    assert req.layer == "google" and req.category == F.WARNING and req.property == "review|aggregateRating|offers" and "product-snippet" in req.doc
    assert not [f for f in out if f.layer == "schemaorg" and f.category in (F.ERROR, F.WARNING)], "the markup itself is valid Schema.org"
    assert all(f.category != F.ERROR for f in out if f.layer == "google")


def test_a_google_requirement_that_is_met_by_any_of_its_alternatives_is_met():
    assert not [f for f in run(node("Product", name="P", aggregateRating={"@type": "AggregateRating", "ratingValue": 5, "reviewCount": 1})) if f.rule_id == "google.missing_required"]


def test_google_recommendations_are_enhancements():
    out = run(node("Article", headline="H"))
    assert {f.property for f in out if f.rule_id == "google.missing_recommended"} >= {"author", "datePublished", "image"}
    assert {f.category for f in out if f.rule_id == "google.missing_recommended"} == {F.ENHANCEMENT}


def test_a_feature_google_has_restricted_or_retired_is_informational_not_a_promise_or_a_fault():
    faq = run(node("FAQPage", mainEntity=[{"@type": "Question", "name": "Q", "acceptedAnswer": {"@type": "Answer", "text": "A"}}]))
    assert [f.category for f in faq if f.rule_id == "google.faq.restricted"] == [F.INFORMATIONAL]
    how = run(node("HowTo", name="H", step=[{"@type": "HowToStep", "text": "s"}]))
    assert [f.category for f in how if f.rule_id == "google.howto.deprecated"] == [F.INFORMATIONAL]
    assert not [f for f in how if f.rule_id.startswith("google.missing")]


def test_google_checks_a_subtype_and_only_a_node_standing_for_the_page():
    # ProfessionalService is a LocalBusiness: it needs a name and an address for the local business result.
    assert {f.property for f in run(node("ProfessionalService", name="X")) if f.rule_id == "google.missing_required"} == {"address"}
    # An Organization embedded as an article's publisher is a detail, not the page's own organization markup.
    out = run(node("Article", headline="H", publisher={"@type": "Organization", "name": "X"}))
    assert not [f for f in out if f.layer == "google" and f.type == "Organization"]


def test_every_google_feature_row_names_the_documentation_it_was_written_from():
    assert google_rules.REVIEWED
    for feature in google_rules.FEATURES:
        assert feature.doc.startswith("https://developers.google.com/search/docs/"), feature.key
        assert load().has_type(feature.type), feature.key


# ── recommendations ──────────────────────────────────────────────────────────

PAGE = {"@type": "WebPage", "@id": URL + "#webpage", "url": URL, "name": "SEO"}


def test_mainEntity_is_recommended_for_a_service_page_with_one_service_and_is_an_enhancement():
    graph = {"@context": CTX, "@graph": [PAGE, {"@type": "Service", "@id": URL + "#service", "name": "SEO", "provider": {"@id": HOME + "#o"}}]}
    [rec] = [f for f in run(graph, page_type="service") if f.rule_id == "recommendation.main_entity"]
    assert rec.category == F.ENHANCEMENT and rec.layer == "recommendation" and rec.auto_fixable and URL + "#service" in rec.recommendation and "not a requirement" in rec.explanation


def test_mainEntity_is_not_recommended_when_it_is_already_set_ambiguous_or_a_business_not_a_service():
    svc = {"@type": "Service", "@id": URL + "#service", "name": "SEO"}
    assert "recommendation.main_entity" not in rules(run({"@context": CTX, "@graph": [{**PAGE, "mainEntity": {"@id": URL + "#service"}}, svc]}, page_type="service"))
    two = {"@context": CTX, "@graph": [PAGE, svc, {**svc, "@id": URL + "#service2"}]}
    assert "recommendation.main_entity" not in rules(run(two, page_type="service")), "two candidates: which is the main one is not for the validator to guess"
    # A ProfessionalService is an Organization: the business that provides the service is not the page's service.
    biz = {"@context": CTX, "@graph": [PAGE, {"@type": "ProfessionalService", "@id": HOME + "#ps", "name": "X", "address": "a"}]}
    assert "recommendation.main_entity" not in rules(run(biz, page_type="service"))
    # Not a page about one thing.
    assert "recommendation.main_entity" not in rules(run({"@context": CTX, "@graph": [PAGE, svc]}, page_type="homepage"))
    # The entity already says it is the page's main entity.
    tied = {"@context": CTX, "@graph": [PAGE, {**svc, "mainEntityOfPage": URL}]}
    assert "recommendation.main_entity" not in rules(run(tied, page_type="service"))


@pytest.mark.parametrize("present", [["Article"], ["BlogPosting"], ["NewsArticle"], ["TechArticle"], ["ScholarlyArticle"], ["Report"], ["LiveBlogPosting"]])
def test_any_article_subtype_satisfies_the_article_expectation(present):
    assert recommendation_rules.satisfied(load(), present, "Article", ("BlogPosting", "NewsArticle"))


def test_a_page_without_any_article_markup_is_an_enhancement_and_one_with_a_subtype_is_not_told_to_add_one():
    from app.schema_tools.expected import find_missing_required

    assert find_missing_required("editorial", ["WebPage"]) == ["Article"]
    assert find_missing_required("editorial", ["TechArticle"]) == ["WebPage"], "a subtype satisfies Article; the baseline also expects the page to be a WebPage"
    assert find_missing_required("editorial", ["TechArticle", "WebPage"]) == []
    page = schema_audit.audit_page("https://site.example/blog/post", "Post", [{"@context": CTX, "@type": "WebPage", "name": "P"}], set())
    miss = [f for f in page["findings"] if f.rule_id == "recommendation.missing_type_required"]
    assert page["page_type"] == "editorial" and miss and miss[0].category == F.ENHANCEMENT and miss[0].layer == "recommendation"
    assert not page["corrections"] or all(c["transform"] != "recommendation.missing_type_required" for c in page["corrections"]), "an enhancement does not count against the page"
    done = schema_audit.audit_page("https://site.example/blog/post", "Post", [{"@context": CTX, "@type": "TechArticle", "headline": "H"}], set())
    assert not [f for f in done["findings"] if f.rule_id == "recommendation.missing_type_required" and f.type == "Article"], "a TechArticle is an Article"


# ── the audit: grouping, counts, and what counts against a page ─────────────


def _page(url, blocks, **kw):
    return schema_audit.audit_page(url, "T", blocks, set(), **kw)


def test_one_template_problem_across_many_pages_is_one_group_with_the_true_page_count():
    audits = [_page(f"https://site.example/p/{i}", [node("Organization", name="X", mentions={"@type": "Thing"}, fooBarBaz=1)]) for i in range(40)]
    groups = {g["template_key"]: g for g in schema_audit.group_findings(audits)}
    g = groups["schemaorg.property_domain|Organization|mentions"]
    assert g["pages"] == 40 and g["occurrences"] == 40 and len(g["sample_urls"]) == schema_audit.SAMPLE_URLS
    assert g["category"] == F.WARNING and g["doc"] and g["recommendation"] and g["example"]["evidence"] == {"mentions": {"@type": "Thing"}} and g["example"]["entity_id"] is None
    assert groups["schemaorg.unknown_property|Organization|fooBarBaz"]["category"] == F.ERROR
    counts = schema_audit.finding_counts(audits)
    assert counts[F.ERROR]["pages"] == 40 and counts[F.ERROR]["groups"] == 1


def test_a_page_counts_once_per_group_however_often_the_finding_repeats_on_it():
    page = _page("https://site.example/p", [{"@context": CTX, "@graph": [node("Organization", name="X", mentions=1)["@type"] and {"@type": "Organization", "@id": f"#o{i}", "name": "X", "mentions": {"@type": "Thing"}} for i in range(5)]}])
    [g] = [g for g in schema_audit.group_findings([page]) if g["template_key"] == "schemaorg.property_domain|Organization|mentions"]
    assert g["pages"] == 1 and g["occurrences"] == 5


def test_only_errors_and_warnings_count_against_a_page_and_enhancements_do_not():
    clean = _page("https://site.example/", [node("Organization", name="X", url=HOME)])
    assert {f.category for f in clean["findings"]} <= {F.ENHANCEMENT, F.INFORMATIONAL} and clean["corrections"] == []
    broken = _page("https://site.example/", [node("Organization", name="X", fooBarBaz=1)])
    assert [c["transform"] for c in broken["corrections"]] == ["schemaorg.unknown_property"] and broken["score"] < clean["score"] or broken["score"] <= clean["score"]


def test_a_finding_carries_everything_needed_to_check_it():
    [f] = [f for f in run(node("Service", **{"@id": URL + "#s"}, name="S", mentions={"@type": "Thing", "name": "SEO"})) if f.rule_id == "schemaorg.property_domain"]
    d = f.as_dict()
    for key in ("rule_id", "layer", "category", "title", "message", "explanation", "recommendation", "doc", "url", "entity_id", "type", "property", "evidence", "auto_fixable", "confidence", "template_key"):
        assert d[key] not in (None, "") or key in ("auto_fixable",), key
    assert d["entity_id"] == URL + "#s" and d["url"] == URL and d["doc"] == "https://schema.org/mentions" and d["template_key"] == "schemaorg.property_domain|Service|mentions"


def test_findings_are_ordered_errors_first_and_are_not_repeated():
    out = run(node("Organization", name="X", fooBarBaz=1, mentions={"@type": "Thing"}))
    assert [F.RANK[f.category] for f in out] == sorted(F.RANK[f.category] for f in out)
    assert len({(f.rule_id, f.entity_id, f.property, str(f.evidence)) for f in out}) == len(out)


# ── the generator pipeline no longer strips valid properties ────────────────


def test_markup_the_tool_generates_keeps_every_property_schema_org_defines_and_drops_only_invented_ones():
    from app.schema_tools.transforms import run_pipeline

    cleaned, corrections = run_pipeline({"@context": CTX, "@graph": [{"@type": "Organization", "@id": HOME + "#o", "name": "X", "disambiguatingDescription": "d", "inventedProperty": 1, "provider": {"@id": HOME + "#o"}}]})
    org = cleaned["@graph"][0]
    assert org["disambiguatingDescription"] == "d" and "provider" in org, "a valid property, and one used on a type it is not defined for, are left for a person to judge"
    assert "inventedProperty" not in org and any("inventedProperty" in c["detail"] for c in corrections)


# ── what real sites write that is valid ──────────────────────────────────────


@pytest.mark.parametrize("value", ["2009", "2009-05", "2009-05-14", "2009-05-14T08:30:00Z"])
def test_a_year_or_a_month_is_a_valid_date(value):
    out = run(node("Organization", name="Co", foundingDate=value), url=HOME)
    assert "schemaorg.property_range" not in rules(out)


@pytest.mark.parametrize("value", ["a long time ago", "2009-13-45x", "May 2009"])
def test_text_that_is_not_a_date_is_still_reported(value):
    out = run(node("Organization", name="Co", foundingDate=value), url=HOME)
    assert "schemaorg.property_range" in rules(out)


def test_query_input_is_a_valid_annotation_on_a_search_action():
    site = node("WebSite", name="Co", url=HOME, potentialAction={"@type": "SearchAction", "target": HOME + "?s={q}", "query-input": "required name=q"})
    out = run(site, url=HOME)
    assert not [f for f in out if f.property == "query-input"]


def test_a_misspelt_property_that_only_looks_like_an_annotation_is_still_unknown():
    out = run(node("Organization", name="Co", **{"nonsense-input": "x"}), url=HOME)
    assert any(f.rule_id == "schemaorg.unknown_property" and f.property == "nonsense-input" for f in out)


def test_generated_markup_keeps_query_input():
    from app.schema_tools.transforms import validate_properties

    graph = [{"@type": "SearchAction", "target": "x", "query-input": "required name=q", "madeUp": 1}]
    out, corrections = validate_properties(graph)
    assert "query-input" in out[0] and "madeUp" not in out[0] and len(corrections) == 1


def test_a_deprecated_property_is_reported_once_as_deprecated_not_as_misplaced():
    out = run(node("VideoObject", name="V", interactionCount="5"), url=HOME)
    assert "schemaorg.deprecated_property" in rules(out)
    assert not about(out, "interactionCount")


# ── what kind of page it is ──────────────────────────────────────────────────


def test_a_blog_post_is_editorial_even_though_the_site_marks_up_its_business_on_every_page():
    from app.schema_tools.page_type import detect_page_type

    assert detect_page_type("https://site.example/blog/some-post", ["BlogPosting", "ProfessionalService", "Organization", "WebPage"]) == "editorial"


def test_a_page_marked_up_only_with_the_sites_business_takes_its_kind_from_its_address():
    from app.schema_tools.page_type import detect_page_type

    assert detect_page_type("https://site.example/blog/some-post", ["ProfessionalService", "Organization"]) == "editorial"


def test_a_page_that_offers_a_service_is_still_a_service_page():
    from app.schema_tools.page_type import detect_page_type

    assert detect_page_type("https://site.example/services/seo", ["Service", "ProfessionalService", "Organization"]) == "service"
