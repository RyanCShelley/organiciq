"""The comparison of a Wikidata candidate with what the site's markup says."""

from __future__ import annotations

from app.schema_tools.wikidata_evidence import Facts, compare

LABELS = {"Q6": "region", "Q7": "genus of mammals", "Q8": "retail company", "Q1": "business", "Q2": "Orlando", "Q3": "information technology", "Q4": "fictional company", "Q5": "Rotterdam"}


def claim(value, rank: str = "normal"):
    return {"mainsnak": {"datavalue": {"value": value}}, "rank": rank}


def item(qid: str):
    return {"id": qid}


def entity(**claims):
    return {"claims": {k: [claim(v) for v in vs] for k, vs in claims.items()}}


SITE = Facts(url="https://www.corvantsolutions.com/", types=["Organization"], places=["Orlando", "FL"], same_as=["https://www.linkedin.com/company/corvant"])


def row(result, key):
    return next(r for r in result["rows"] if r["key"] == key)


def test_the_real_item_is_a_strong_match():
    e = entity(P856=["https://corvantsolutions.com"], P31=[item("Q1")], P159=[item("Q2")], P452=[item("Q3")], P4264=["corvant"])
    r = compare(e, LABELS, SITE)
    assert r["verdict"] == "strong"
    assert row(r, "website")["status"] == "match"
    assert row(r, "hq")["status"] == "match"
    assert row(r, "profiles")["status"] == "match"
    assert row(r, "industry")["wikidata"] == "information technology"


def test_a_fictional_namesake_is_not_this_one():
    r = compare(entity(P31=[item("Q4")]), LABELS, SITE)
    assert row(r, "instance")["status"] == "conflict"
    assert r["verdict"] == "unlikely"


def test_a_different_website_is_decisive():
    r = compare(entity(P856=["https://corvantgroup.eu"], P159=[item("Q5")], P452=[item("Q3")]), LABELS, SITE)
    assert row(r, "website")["status"] == "conflict"
    assert row(r, "hq")["status"] == "conflict"
    assert r["verdict"] == "unlikely"


def test_a_sparse_item_is_only_possible_and_nothing_is_invented():
    r = compare(entity(P31=[item("Q1")]), LABELS, SITE)
    assert row(r, "website")["status"] == "none"
    assert r["verdict"] == "possible"
    assert r["conflicts"] == 0


def test_profiles_the_site_lacks_are_reported():
    r = compare(entity(P856=["https://corvantsolutions.com"], P2013=["corvant"]), LABELS, Facts(url=SITE.url, types=["Organization"]))
    assert row(r, "profiles")["status"] == "missing"
    assert "https://www.facebook.com/corvant" in r["profiles"]


def test_deprecated_claims_are_ignored():
    e = {"claims": {"P856": [claim("https://other.example", rank="deprecated"), claim("https://corvantsolutions.com")]}}
    assert row(compare(e, LABELS, SITE), "website")["status"] == "match"


def test_a_site_with_no_organization_markup_gives_no_conflicts():
    r = compare(entity(P856=["https://corvantsolutions.com"], P159=[item("Q2")]), LABELS, Facts())
    assert r["conflicts"] == 0
    assert row(r, "website")["status"] == "none"


def test_a_different_website_alone_does_not_outweigh_other_matches():
    """A brand can keep its site at another address than Wikidata lists; with the place and kind agreeing it is weak, not ruled out."""
    r = compare(entity(P856=["https://about.example"], P31=[item("Q1")], P159=[item("Q2")]), LABELS, SITE)
    assert row(r, "website")["status"] == "conflict"
    assert r["verdict"] == "weak"


def test_only_the_preferred_profile_of_each_kind_is_read():
    r = compare(entity(P2013=["corvant", "corvantregional"]), LABELS, Facts(url=SITE.url))
    assert r["profiles"] == ["https://www.facebook.com/corvant"]


def test_a_region_or_a_genus_is_not_an_organization():
    for q in ("Q6", "Q7"):
        r = compare(entity(P31=[item(q)]), LABELS, SITE)
        assert row(r, "instance")["status"] == "conflict"
        assert r["verdict"] == "unlikely"


def test_a_company_of_any_kind_is_compatible():
    assert row(compare(entity(P31=[item("Q8")]), LABELS, SITE), "instance")["status"] == "match"
