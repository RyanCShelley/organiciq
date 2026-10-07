"""5a — the markup that says who the brand is.

This rule shipped once with no test, and its first run against two real
sites accused both of missing every property on their homepage. Both were
correct: the crawler stores the whole JSON-LD document on each row, so the
check was reading the `@context` wrapper. Hence the fixtures below are
shaped the way the crawler actually stores them, not the way the rule
would like them.
"""

from __future__ import annotations

from app.decisions.actions.entity import EntityBlock, check_entity


def _flat(url: str, node: dict, *, is_homepage: bool = False) -> EntityBlock:
    """A document that is a single node, with no `@graph`."""
    declared = node["@type"]
    return EntityBlock(
        url=url,
        schema_type=declared if isinstance(declared, str) else declared[0],
        raw=node,
        is_homepage=is_homepage,
    )


COMPLETE = {
    "@type": "Organization",
    "name": "Example",
    "url": "https://example.com",
    "logo": "https://example.com/logo.png",
    "sameAs": ["https://www.linkedin.com/company/example"],
}


# ── Nothing wrong ──


def test_a_complete_homepage_block_passes():
    assert check_entity([_flat("https://example.com/", COMPLETE, is_homepage=True)], domain="example.com") == []


def test_no_entity_block_is_not_a_failure():
    """Having no Organization markup is a different rule's problem. This
    one corrects markup that exists; it does not demand markup."""
    block = _flat("https://example.com/blog/a", {"@type": "Article", "name": "A"})
    assert check_entity([block], domain="example.com") == []


def test_www_and_the_apex_are_the_same_host():
    node = {**COMPLETE, "url": "https://www.example.com"}
    assert check_entity([_flat("https://example.com/", node)], domain="example.com") == []


# ── One name ──


def test_two_names_across_the_site_conflict():
    blocks = [
        _flat("https://example.com/", COMPLETE, is_homepage=True),
        _flat("https://example.com/about", {**COMPLETE, "name": "Example Inc"}),
    ]
    failures = check_entity(blocks, domain="example.com")
    assert [f.check for f in failures] == ["name_conflict"]
    assert "Example" in failures[0].detail and "Example Inc" in failures[0].detail


def test_the_same_name_everywhere_is_fine():
    blocks = [
        _flat("https://example.com/", COMPLETE, is_homepage=True),
        _flat("https://example.com/about", COMPLETE),
    ]
    assert check_entity(blocks, domain="example.com") == []


# ── The url property ──


def test_a_url_on_another_host_hands_the_identity_away():
    node = {**COMPLETE, "url": "https://squarespace.com/example"}
    failures = check_entity([_flat("https://example.com/", node)], domain="example.com")
    assert [f.check for f in failures] == ["url_host"]


# ── Homepage properties ──


def test_a_local_business_homepage_needs_an_address_and_a_phone():
    node = {**COMPLETE, "@type": "LocalBusiness"}
    failures = check_entity([_flat("https://example.com/", node, is_homepage=True)], domain="example.com")
    assert [f.check for f in failures] == ["homepage_properties"]
    assert "`address`" in failures[0].detail and "`telephone`" in failures[0].detail


def test_an_inner_page_is_not_held_to_the_homepage_bar():
    """The homepage block is the one an engine reads. Demanding `sameAs`
    on every page would turn an hour's correction into a site-wide edit."""
    node = {"@type": "Organization", "name": "Example", "url": "https://example.com"}
    assert check_entity([_flat("https://example.com/about", node)], domain="example.com") == []


def test_an_empty_property_counts_as_missing():
    node = {**COMPLETE, "logo": "", "sameAs": []}
    failures = check_entity([_flat("https://example.com/", node, is_homepage=True)], domain="example.com")
    assert "`logo`" in failures[0].detail and "`sameAs`" in failures[0].detail



# ── The whole document, not the node ──


def _graph_block(url: str, node: dict, *, is_homepage: bool = False) -> EntityBlock:
    """A block as the crawler actually stores it: the whole JSON-LD
    document, with one row per type found anywhere inside it."""
    return EntityBlock(
        url=url,
        schema_type=node["@type"] if isinstance(node["@type"], str) else node["@type"][0],
        raw={
            "@context": "https://schema.org",
            "@graph": [{"@type": "WebSite", "name": "SMA Marketing"}, node],
        },
        is_homepage=is_homepage,
    )


def test_properties_are_read_from_the_node_not_the_wrapper():
    """The crawler stores the whole document on every row. Reading `name`
    off that read the `@context` wrapper, so every correctly marked-up
    homepage reported all four properties missing — which is how this
    rule's first run accused two sites that had nothing wrong."""
    block = _graph_block(
        "https://example.com/",
        {
            "@type": "Organization",
            "name": "Example",
            "url": "https://example.com",
            "logo": {"@type": "ImageObject", "url": "https://example.com/logo.png"},
            "sameAs": ["https://www.linkedin.com/company/example"],
        },
        is_homepage=True,
    )
    assert check_entity([block], domain="example.com") == []


def test_a_node_nested_in_a_graph_is_still_checked():
    block = _graph_block(
        "https://example.com/",
        {"@type": "Organization", "name": "Example", "url": "https://example.com"},
        is_homepage=True,
    )
    failures = check_entity([block], domain="example.com")
    assert [f.check for f in failures] == ["homepage_properties"]
    assert "`logo`" in failures[0].detail and "`sameAs`" in failures[0].detail


def test_a_graph_url_pointing_elsewhere_is_still_caught():
    block = _graph_block(
        "https://example.com/",
        {"@type": "Organization", "name": "Example", "url": "https://other.test"},
    )
    assert [f.check for f in check_entity([block], domain="example.com")] == ["url_host"]


def test_a_type_with_no_matching_node_falls_back_to_the_document():
    """A row whose type came from a nested entry we do not walk should not
    crash or silently pass; the document itself is the best available."""
    block = EntityBlock(
        url="https://example.com/",
        schema_type="Organization",
        raw={"name": "Example", "url": "https://example.com"},
        is_homepage=True,
    )
    failures = check_entity([block], domain="example.com")
    assert [f.check for f in failures] == ["homepage_properties"]
