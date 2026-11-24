"""A page the site does not have.

The hard part is being sure it is missing. A tracked term with no map entry
and no suggestion looked like a gap on ACCTek, and four of its six were pages
the site already has.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.decisions.content_gaps import (
    MIN_VOLUME,
    NearPage,
    TermGap,
    c1_write_the_page,
    content_words,
    fold_variants,
    rank_for_content,
)
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.decision import KeywordTarget
from app.models.seranking import FactSerKeyword, FactSerKeywordMetric
from app.services.content_gap_signals import MIN_CRAWLED_PAGES, scan_term_gaps


def _gap(**overrides) -> TermGap:
    fields = {
        "term": "aeo agency", "volume": 480.0, "difficulty": 12.0,
        "pages_searched": 300, "best_overlap": 0.5,
    }
    fields.update(overrides)
    return TermGap(**fields)


# ── The brief ──


def test_c1_fires_on_a_term_with_volume_and_a_known_difficulty():
    found = c1_write_the_page(_gap())
    assert found is not None
    assert found.action_id == "C-1"
    assert found.term == "aeo agency"
    assert found.metric_key == "term_position"
    assert found.target_url == ""  # there is no page yet
    assert found.check_after_days == 90


def test_c1_states_what_its_claim_of_absence_rests_on():
    assert "the closest carries 50% of its words" in c1_write_the_page(_gap()).why
    never = c1_write_the_page(_gap(absent_words=("orlando",)))
    assert "mentions “orlando”" in never.why
    recorded = c1_write_the_page(_gap(recorded_no_page=True))
    assert "recorded in the keyword map as having no page" in recorded.why


def test_c1_does_not_fire_below_the_volume_floor():
    assert c1_write_the_page(_gap(volume=MIN_VOLUME - 1)) is None


def test_c1_will_not_score_a_term_whose_difficulty_is_unknown():
    """Ranking by volume alone would put the term nobody can win first."""
    assert c1_write_the_page(_gap(difficulty=None)) is None


def test_difficulty_discounts_volume():
    hard = _gap(term="a", volume=9900.0, difficulty=63.0)
    easy = _gap(term="b", volume=480.0, difficulty=12.0)
    assert hard.opportunity == 9900 * 0.37
    assert easy.opportunity == 480 * 0.88
    assert [g.term for g in rank_for_content([easy, hard])] == ["a", "b"]


def test_the_brief_names_variants_the_page_has_to_cover_and_where_to_link_from():
    found = c1_write_the_page(
        _gap(
            also_covers=(("seo consultancy", 120.0),),
            nearest=(NearPage(url="https://x.test/seo", title="SEO", shared=("seo",)),),
        )
    )
    text = " ".join(found.steps)
    assert "“seo consultancy” (120)" in text
    assert "https://x.test/seo (shares seo)" in text
    assert "keyword map" in found.steps[-1]


def test_variants_of_one_subject_share_a_page():
    folded = fold_variants(
        [
            _gap(term="pressure washing", volume=9000.0),
            _gap(term="commercial pressure washing", volume=9900.0),
            _gap(term="paver sealing", volume=300.0),
        ]
    )
    assert [g.term for g in folded] == ["commercial pressure washing", "paver sealing"]
    assert folded[0].also_covers == (("pressure washing", 9000.0),)


def test_words_are_compared_without_filler_or_plurals():
    assert content_words("plumbers near me") == content_words("Plumber")
    assert content_words("the best SEO services") == frozenset({"seo"})


# ── The scan ──

DAY = date(2026, 10, 1)


def _page(db, client_id, slug, title=None, headings=()):
    url = f"https://example.com/{slug}"
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(), client_id=client_id, source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=DAY, raw_url=url, normalized_url=url, status_code=200,
            indexable=True, word_count=800, inbound_internal_links=5,
            inbound_editorial_links=3, redirect_count=0, title=title,
            sections=[{"heading": h} for h in headings],
        )
    )


def _filler(db, client_id, n=MIN_CRAWLED_PAGES):
    for i in range(n):
        _page(db, client_id, f"filler-{i}", title=f"Filler {i}")


def _term(db, client_id, keyword, *, volume=500, difficulty=20, mapped_to=None, no_page=False,
          position=None, ranking_url=None):
    db.add(
        FactSerKeyword(
            id=uuid4(), client_id=client_id, site_engine_id="1",
            keyword_id=str(uuid4())[:8], keyword=keyword, volume=volume,
            current_position=position, ranking_url=ranking_url,
        )
    )
    db.add(
        FactSerKeywordMetric(
            id=uuid4(), client_id=client_id, keyword=keyword, source="us",
            volume=volume, difficulty=difficulty, data_found=True, fetched_at=DAY,
        )
    )
    if mapped_to is not None or no_page:
        db.add(
            KeywordTarget(
                id=uuid4(), client_id=client_id, keyword=keyword,
                target_url=mapped_to, source="confirmed",
            )
        )


def test_a_term_no_page_carries_is_a_gap(db, client_a):
    _filler(db, client_a.id)
    _term(db, client_a.id, "aeo agency")
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert [g.term for g in scan.gaps] == ["aeo agency"]
    assert scan.gaps[0].pages_searched == MIN_CRAWLED_PAGES


def test_a_term_a_page_already_carries_is_not(db, client_a):
    """ACCTek's /vciso and /structured-cabling, which an unmapped-term test called gaps."""
    _filler(db, client_a.id)
    _page(db, client_a.id, "structured-cabling", title="Structured Cabling - Acme")
    _page(db, client_a.id, "guides", title="Guides", headings=["What is a vCISO?"])
    _term(db, client_a.id, "structured cabling")
    _term(db, client_a.id, "vciso")
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert scan.gaps == []
    assert scan.summary["covered"] == 2


def test_a_term_mapped_to_a_page_is_somebodys_decision(db, client_a):
    _filler(db, client_a.id)
    _term(db, client_a.id, "aeo agency", mapped_to="https://example.com/filler-1")
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert scan.gaps == [] and scan.summary["mapped"] == 1


def test_a_term_recorded_as_having_no_page_is_a_gap_even_if_words_match(db, client_a):
    _filler(db, client_a.id)
    _page(db, client_a.id, "seo", title="SEO consulting agency")
    _term(db, client_a.id, "seo consulting agency", no_page=True)
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert [g.term for g in scan.gaps] == ["seo consulting agency"]
    assert scan.gaps[0].recorded_no_page is True


def test_a_term_already_ranking_has_a_page(db, client_a):
    _filler(db, client_a.id)
    _term(db, client_a.id, "aeo agency", position=14, ranking_url="https://example.com/x")
    db.commit()
    assert scan_term_gaps(db, client_a).gaps == []


def test_a_term_without_volume_and_difficulty_is_set_aside_and_counted(db, client_a):
    _filler(db, client_a.id)
    _term(db, client_a.id, "aeo agency", difficulty=None)
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert scan.gaps == [] and scan.summary["no_metrics"] == 1


def test_a_crawl_too_small_to_prove_absence_blocks_the_scan(db, client_a):
    """Fourteen clients have a crawl of zero or one page."""
    _page(db, client_a.id, "home", title="Home")
    _term(db, client_a.id, "aeo agency")
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert scan.gaps == []
    assert "too few to say a term has no page" in scan.explain_empty()


def test_an_empty_scan_says_what_it_checked(db, client_a):
    _filler(db, client_a.id)
    _page(db, client_a.id, "vciso", title="vCISO")
    _term(db, client_a.id, "vciso")
    db.commit()
    assert "1 already covered" in scan_term_gaps(db, client_a).explain_empty()


def test_an_inflected_form_still_meets_the_page_that_covers_it():
    """Aquaman's "leaking hot tub" beside /blog/find-a-hot-tub-leak-quickly."""
    assert content_words("leaking hot tub") <= content_words(
        "Find A Hot Tub Leak Quickly https://x.test/blog/find-a-hot-tub-leak-quickly"
    )
    assert content_words("washing") == content_words("washer")


def test_a_url_contributes_its_path_not_its_host():
    from urllib.parse import urlsplit

    assert "com" not in content_words(urlsplit("https://example.com/blog/x").path)


def test_it_is_a_pronoun_in_a_question_and_an_industry_otherwise():
    assert "it" not in content_words("is it safe to swim")
    assert "it" in content_words("it support syracuse")


def test_intent_codes_are_spelled_out():
    assert "local / commercial" in c1_write_the_page(_gap(intents=("L", "C"))).steps[0]


def test_a_topic_a_page_mostly_answers_is_covered(db, client_a):
    """Aquaman's "is it safe to swim in cloudy pool water" beside /blog/are-cloudy-pools-safe."""
    _filler(db, client_a.id)
    _page(db, client_a.id, "blog/are-cloudy-pools-safe", title="Are Cloudy Pools Safe?")
    _page(db, client_a.id, "water", title="Swim water")
    _term(db, client_a.id, "is it safe to swim in cloudy pool water")
    db.commit()
    assert scan_term_gaps(db, client_a).gaps == []


def test_a_word_the_site_never_uses_is_a_gap_whatever_else_matches(db, client_a):
    """Aquaman's "pool leak detection orlando": three of four words are everywhere."""
    _filler(db, client_a.id)
    _page(db, client_a.id, "pool-leak-detection", title="Pool Leak Detection")
    _term(db, client_a.id, "pool leak detection orlando")
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert [g.term for g in scan.gaps] == ["pool leak detection orlando"]
    assert scan.gaps[0].absent_words == ("orlando",)


def test_british_and_american_spellings_are_one_word():
    assert content_words("carbon fibre") == content_words("carbon fiber")
    assert content_words("organic search optimisation") == content_words("organic search optimization")
    assert content_words("colour options") == content_words("color options")


def test_a_single_letter_is_not_a_word_to_match_on():
    assert content_words("carbon fiber i beam") == content_words("carbon fiber beam")
    assert "88" in content_words("helo 88")


# ── Pure noise, topicality, and brand rules ──


def test_is_noise_query_rejects_auth_jobs_utility_files_urls_and_ugc_but_keeps_b2b():
    from app.decisions.content_gaps import is_noise_query

    noisy = [
        "",
        "ab",
        "12345",
        "---",
        "site:example.com hvac",
        "inurl:pricing hvac",
        "https://rival.com/services",
        "www.rival.com",
        "support@rival.com",
        "rival.com",
        "customer portal login",
        "sign in",
        "forgot my password",
        "wp-admin",
        "hvac technician jobs",
        "acme careers",
        "hvac tech salary",
        "glassdoor hvac",
        "customer service",
        "phone number",
        "privacy policy",
        "terms of service",
        "unsubscribe",
        "service manual pdf",
        "free download",
        "reddit hvac advice",
        "wikipedia furnace",
        "yelp ac repair",
        "bbb hvac ratings",
        "youtube furnace repair",
        "chatgpt login",
        "hubspot pricing",
    ]
    for q in noisy:
        assert is_noise_query(q) is True, f"expected noise for {q!r}"

    kept = [
        "managed it support",
        "password manager",
        "asp.net migration services",
        "node.js performance audit",
        "hvac service by zip code",
        "heat pump installation",
        "commercial furnace repair",
    ]
    for q in kept:
        assert is_noise_query(q) is False, f"unexpectedly filtered {q!r}"


def test_is_noise_query_platform_context_modes():
    from app.decisions.content_gaps import is_noise_query

    # strict_platforms=True allows a platform only when present in core_vocab (allowed_words)
    assert is_noise_query("youtube seo tips", strict_platforms=True) is True
    assert (
        is_noise_query(
            "youtube seo tips",
            strict_platforms=True,
            allowed_words=content_words("youtube channel seo"),
        )
        is False
    )
    # strict_platforms=False (tracked terms) keeps intentional platform strategy terms
    # unless paired with navigational/utility modifiers
    assert is_noise_query("linkedin ads", strict_platforms=False) is False
    assert is_noise_query("youtube seo", strict_platforms=False) is False
    assert is_noise_query("linkedin login", strict_platforms=False) is True
    assert is_noise_query("hubspot pricing", strict_platforms=False) is True
    assert is_noise_query("semrush alternatives", strict_platforms=False) is True


def test_is_topically_relevant_strips_generics_and_preserves_sparse_sites():
    from app.decisions.content_gaps import is_topically_relevant

    sparse = content_words("furnace repair filler 0")
    assert is_topically_relevant(content_words("heat pump installation"), core_vocab=sparse) is True

    hvac_vocab = content_words(
        "furnace repair ac installation duct cleaning thermostat heat pump hvac maintenance"
    )
    assert is_topically_relevant(content_words("car insurance cost"), core_vocab=hvac_vocab) is False
    assert is_topically_relevant(content_words("best local pricing guide"), core_vocab=hvac_vocab) is False
    assert is_topically_relevant(content_words("heat pump rebate orlando"), core_vocab=hvac_vocab) is True


def test_brand_terms_and_is_navigational_handle_short_and_two_char_brands_safely():
    from types import SimpleNamespace

    from app.services.page_signals import brand_terms, is_navigational

    sma = SimpleNamespace(
        client_name="SMA",
        domain="https://www.sma.com/services",
        brand_aliases=["  SMA   Marketing ", "it"],
    )
    terms = brand_terms(sma)
    assert {"sma", "sma.com", "sma marketing"} <= terms
    assert "it" not in terms
    assert is_navigational("sma reviews", terms) is True
    assert is_navigational("SMA's pricing", terms) is True
    assert is_navigational("small business seo", terms) is False
    assert is_navigational("smart thermostat guide", terms) is False

    hyphen = SimpleNamespace(
        client_name="Boys",
        domain="boys-electrical.com",
        brand_aliases=[],
    )
    assert "boys electrical" in brand_terms(hyphen)

    two_char = SimpleNamespace(client_name="IT", domain="it.com", brand_aliases=[])
    two_terms = brand_terms(two_char)
    assert "it" not in two_terms
    assert is_navigational("it services", two_terms) is False
    assert is_navigational("it.com login", two_terms) is True

    smith = SimpleNamespace(
        client_name="Smith's Electrical",
        domain="smithelectrical.com",
        brand_aliases=[],
    )
    smith_terms = brand_terms(smith)
    assert is_navigational("smith's electrical", smith_terms) is True
    assert is_navigational("smith’s electrical", smith_terms) is True
    assert is_navigational("smith’s electrical contractor", smith_terms) is True
    assert is_navigational("smith electrical", smith_terms) is True

    acme = SimpleNamespace(
        client_name="Acme Electrical",
        domain="acmeelectrical.com",
        brand_aliases=[],
    )
    acme_terms = brand_terms(acme)
    assert is_navigational("acme electrical", acme_terms) is True
    assert is_navigational("acme's electrical", acme_terms) is True
    assert is_navigational("acme’s electrical", acme_terms) is True
    assert is_navigational("acme-electrical", acme_terms) is False


# ── Tracked-term scan filtering ──


def test_watch_target_excluded_removes_tracked_gap(db, client_a):
    from app.models.watch_target import WatchTarget

    _filler(db, client_a.id)
    _term(db, client_a.id, "boiler repair")
    _term(db, client_a.id, "commercial hvac maintenance")
    db.add(
        WatchTarget(
            id=uuid4(),
            client_id=client_a.id,
            kind="keyword",
            item_key="k-boiler",
            text="  Boiler   Repair  ",
            state="excluded",
        )
    )
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert [g.term for g in scan.gaps] == ["commercial hvac maintenance"]
    assert scan.summary["excluded"] == 1


def test_short_brand_rival_and_llm_patterns_filtered_in_tracked_scan(db, client_a):
    from app.models.llm_visibility import ClientLlmSettings

    client_a.client_name = "SMA"
    client_a.domain = "sma.com"
    client_a.competitor_domains = ["ibm.com"]
    _filler(db, client_a.id)
    db.add(
        ClientLlmSettings(
            id=uuid4(),
            client_id=client_a.id,
            brand_name="SMA Marketing",
            brand_patterns=["sma agency"],
            competitors={
                "rival-hvac.com": {
                    "name": "Rival HVAC",
                    "patterns": ["rival heating"],
                }
            },
        )
    )
    _term(db, client_a.id, "sma reviews")
    _term(db, client_a.id, "sma agency pricing")
    _term(db, client_a.id, "ibm cloud audit")
    _term(db, client_a.id, "rival heating reviews")
    _term(db, client_a.id, "small business seo")
    db.commit()

    scan = scan_term_gaps(db, client_a)
    assert [g.term for g in scan.gaps] == ["small business seo"]
    assert scan.summary["brand"] == 4


def test_navigational_utility_and_ugc_tracked_terms_excluded_while_b2b_and_platform_strategy_pass(
    db, client_a
):
    _filler(db, client_a.id)
    for bad in (
        "customer portal login",
        "hvac careers",
        "service manual pdf",
        "support phone number",
        "reddit hvac advice",
        "facebook login",
        "hubspot pricing",
    ):
        _term(db, client_a.id, bad)
    _term(db, client_a.id, "managed it support")
    _term(db, client_a.id, "linkedin ads")
    db.commit()

    scan = scan_term_gaps(db, client_a)
    assert {g.term for g in scan.gaps} == {"managed it support", "linkedin ads"}
    assert scan.summary["noise"] == 7


def test_is_topically_relevant_rejects_generic_cross_domain_and_unstemmed_modifiers():
    from app.decisions.content_gaps import is_topically_relevant

    hvac_vocab = content_words(
        "furnace repair ac installation duct cleaning thermostat heat pump "
        "hvac maintenance inspection plan test system better filler differences"
    )
    for bad in (
        "iphone repair",
        "carpet cleaning",
        "solar panel installation",
        "dental plan",
        "blood test",
        "gaming system",
        "better comparison guide",
        "differences comparison guide",
        "filler content guide",
    ):
        assert is_topically_relevant(content_words(bad), core_vocab=hvac_vocab) is False, (
            f"expected off-topic for {bad!r}"
        )

    for good in (
        "furnace repair",
        "duct cleaning",
        "heat pump installation",
        "commercial hvac maintenance",
    ):
        assert is_topically_relevant(content_words(good), core_vocab=hvac_vocab) is True, (
            f"expected relevant for {good!r}"
        )


def test_brand_terms_and_rival_domains_ignore_none_and_malformed_urls(db, client_a):
    from types import SimpleNamespace

    from app.models.llm_visibility import ClientLlmSettings
    from app.services.page_signals import (
        brand_terms,
        effective_brand_terms,
        rival_brand_terms_for_domains,
    )

    c = SimpleNamespace(
        client_name="Test Co",
        domain="testco.com",
        brand_aliases=[None, "  "],
    )
    assert "none" not in brand_terms(c)

    client_a.client_name = "Test Two"
    client_a.domain = "testtwo.com"
    db.add(
        ClientLlmSettings(
            id=uuid4(),
            client_id=client_a.id,
            brand_name="Test Two",
            brand_patterns=[None, "  "],
        )
    )
    db.commit()
    assert "none" not in effective_brand_terms(db, client_a)

    rival_terms = rival_brand_terms_for_domains(
        ["https://", "http://", "/", "www.", "", None, "https://www.Rival.com:8080/x", "not-a-domain"]
    )
    assert rival_terms == {"rival.com", "rival"}


def test_fold_variants_preserves_nested_also_covers_and_scales_fast():
    import time
    from app.decisions.content_gaps import DemandGap

    inner_folded = fold_variants(
        [
            DemandGap(term="heat pump rebate", impressions=500, clicks=10, position=20),
            DemandGap(term="heat pump rebate orlando", impressions=250, clicks=5, position=22),
        ]
    )
    outer = fold_variants(
        [
            *inner_folded,
            DemandGap(
                term="florida heat pump rebate",
                impressions=0,
                clicks=0,
                position=None,
                volume=800,
                difficulty=25,
            ),
        ]
    )
    assert len(outer) == 1
    assert outer[0].term == "florida heat pump rebate"
    assert dict(outer[0].also_covers) == {
        "heat pump rebate": 500.0,
        "heat pump rebate orlando": 250.0,
    }

    many = [
        DemandGap(
            term=f"alpha{i} beta{i} topic{i}",
            impressions=5000 - i,
            clicks=10,
            position=20.0,
        )
        for i in range(2000)
    ]
    t0 = time.perf_counter()
    folded = fold_variants(many)
    elapsed = time.perf_counter() - t0
    assert len(folded) == 2000
    assert elapsed < 0.5


def test_watch_target_excluded_matches_punctuation_variants_in_tracked_scan(db, client_a):
    from app.models.watch_target import WatchTarget

    _filler(db, client_a.id)
    _term(db, client_a.id, "heat pump sizing")
    _term(db, client_a.id, "furnace installation cost")
    _term(db, client_a.id, "commercial hvac maintenance")
    db.add(
        WatchTarget(
            id=uuid4(),
            client_id=client_a.id,
            kind="keyword",
            item_key="k-hp",
            text="heat-pump sizing",
            state="excluded",
        )
    )
    db.add(
        WatchTarget(
            id=uuid4(),
            client_id=client_a.id,
            kind="keyword",
            item_key="k-furnace",
            text="furnace installation cost?",
            state="excluded",
        )
    )
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert [g.term for g in scan.gaps] == ["commercial hvac maintenance"]
    assert scan.summary["excluded"] == 2


def test_stopword_only_tracked_term_filtered_and_fold_variants_empty_lead_safe(db, client_a):
    from app.decisions.content_gaps import DemandGap

    folded = fold_variants(
        [
            DemandGap(term="how to do it", impressions=1000, clicks=10, position=20),
            DemandGap(term="best company services", impressions=800, clicks=5, position=20),
            DemandGap(term="commercial hvac maintenance", impressions=500, clicks=5, position=20),
            DemandGap(term="geothermal heating repair", impressions=400, clicks=4, position=20),
        ]
    )
    assert [g.term for g in folded] == [
        "how to do it",
        "commercial hvac maintenance",
        "geothermal heating repair",
    ]
    assert folded[0].also_covers == (("best company services", 800.0),)

    _filler(db, client_a.id)
    _term(db, client_a.id, "how to do it", volume=1000)
    _term(db, client_a.id, "best company services", volume=900)
    _term(db, client_a.id, "geothermal heating repair", volume=400)
    db.commit()

    scan = scan_term_gaps(db, client_a)
    assert [g.term for g in scan.gaps] == ["geothermal heating repair"]
    assert scan.summary["noise"] == 2


def test_programmes_spelling_normalized_to_program_in_topical_relevance():
    from app.decisions.content_gaps import is_topically_relevant

    assert content_words("programmes") == content_words("program") == frozenset({"program"})
    hvac_vocab = content_words(
        "furnace repair ac installation duct cleaning thermostat heat pump hvac maintenance programmes"
    )
    assert is_topically_relevant(content_words("software programmes"), core_vocab=hvac_vocab) is False


def test_valid_domain_host_and_rival_domains_strip_http_userinfo():
    from app.services.page_signals import _valid_domain_host, rival_brand_terms_for_domains

    assert _valid_domain_host("https://user:pass@rival.com:8080/path?x=1") == "rival.com"
    assert _valid_domain_host("user:pass@rival.com:8080/path") == "rival.com"
    assert _valid_domain_host("https://user:pass@www.rival-two.com:8443/about?x=1#y") == "rival-two.com"
    assert _valid_domain_host("acme.com?foo=bar") == "acme.com"
    assert _valid_domain_host("acme.com#frag") == "acme.com"
    assert _valid_domain_host("acme.com?foo=bar@evil.com") == "acme.com"
    assert _valid_domain_host("acme.com#frag@evil.com") == "acme.com"
    assert _valid_domain_host("www.acme.com?foo=bar#frag") == "acme.com"
    for bad in (
        "https://user:pass@localhost:8080",
        "https://user:pass@",
        "https://user:pass@:8080",
        "https://user:pass@rival.com:",
    ):
        assert _valid_domain_host(bad) == ""

    assert rival_brand_terms_for_domains(
        [
            "https://user:pass@rival.com:8080/path?x=1",
            "user:pass@rival.com:8080/path",
            "https://user:pass@www.rival-two.com:8443/about",
            "https://user:pass@localhost:8080",
            "https://user:pass@",
            "https://user:pass@:8080",
            "https://user:pass@rival.com:",
        ]
    ) == {"rival.com", "rival", "rival-two.com", "rival-two", "rival two"}


def test_hyphenated_brand_industry_rival_filtered_while_geo_industry_preserved_in_tracked_scan(
    db, client_a, client_b
):
    client_a.client_name = "Boys Electrical"
    client_a.domain = "boys-electrical.com"
    client_a.competitor_domains = [
        "jones-electrical.com",
        "acme-electric.com",
        "orlando-electrical.com",
        "palm-bay-electrical.com",
    ]
    for slug, title in (
        ("panel-upgrade", "Electrical Panel Upgrades"),
        ("wiring", "Residential Wiring"),
        ("lighting", "Commercial Lighting Installation"),
        ("ev-charger", "EV Charger Installation"),
        ("surge-protection", "Whole Home Surge Protection"),
        ("generators", "Standby Generator Wiring"),
        ("troubleshooting", "Electrical Troubleshooting"),
        ("outlets", "GFCI Outlet Replacement"),
        ("inspections", "Electrical Safety Inspections"),
        ("ceiling-fans", "Ceiling Fan Installation"),
    ):
        _page(db, client_a.id, slug, title=title)
    _term(db, client_a.id, "jones electrical", volume=450, difficulty=20)
    _term(db, client_a.id, "jones electrical contractor", volume=450, difficulty=20)
    _term(db, client_a.id, "acme electric", volume=450, difficulty=20)
    _term(db, client_a.id, "orlando electrical reviews", volume=450, difficulty=20)
    _term(db, client_a.id, "orlando electrical contractor", volume=450, difficulty=20)
    _term(db, client_a.id, "palm bay electrical", volume=450, difficulty=20)
    db.commit()

    scan = scan_term_gaps(db, client_a)
    assert {g.term for g in scan.gaps} == {
        "orlando electrical contractor",
        "palm bay electrical",
    }
    assert scan.summary["brand"] == 4

    client_b.client_name = "Smith HVAC"
    client_b.domain = "smith-hvac.com"
    client_b.competitor_domains = ["jones-hvac.com"]
    for slug, title in (
        ("ac-repair", "AC Repair Services"),
        ("furnace-repair", "Furnace Repair"),
        ("hvac-maintenance", "HVAC Maintenance Plans"),
        ("duct-cleaning", "Air Duct Cleaning"),
        ("air-conditioning-installation", "Air Conditioning Installation"),
        ("thermostat-upgrade", "Smart Thermostat Installation"),
        ("indoor-air-quality", "Indoor Air Quality Testing"),
        ("heat-pumps", "Heat Pump Systems"),
        ("boiler-service", "Boiler Service and Inspection"),
        ("commercial-hvac", "Commercial HVAC Contractors"),
    ):
        _page(db, client_b.id, slug, title=title)
    _term(db, client_b.id, "jones hvac", volume=450, difficulty=20)
    _term(db, client_b.id, "hvac maintenance checklist", volume=450, difficulty=20)
    db.commit()

    scan_hvac = scan_term_gaps(db, client_b)
    assert [g.term for g in scan_hvac.gaps] == ["hvac maintenance checklist"]
    assert scan_hvac.summary["brand"] == 1


def test_primary_market_surname_city_emd_rival_preserved_in_tracked_scan(db, client_a):
    client_a.client_name = "Smith HVAC"
    client_a.domain = "smith-hvac.com"
    client_a.competitor_domains = ["jackson-hvac.com"]
    client_a.primary_market = None
    for slug, title in (
        ("ac-repair", "AC Repair Services"),
        ("furnace-repair", "Furnace Repair"),
        ("hvac-maintenance", "HVAC Maintenance Plans"),
        ("duct-cleaning", "Air Duct Cleaning"),
        ("air-conditioning-installation", "Air Conditioning Installation"),
        ("thermostat-upgrade", "Smart Thermostat Installation"),
        ("indoor-air-quality", "Indoor Air Quality Testing"),
        ("heat-pumps", "Heat Pump Systems"),
        ("boiler-service", "Boiler Service and Inspection"),
        ("commercial-hvac", "Commercial HVAC Contractors"),
    ):
        _page(db, client_a.id, slug, title=title)
    _term(db, client_a.id, "jackson hvac", volume=450, difficulty=20)
    _term(db, client_a.id, "jackson hvac reviews", volume=300, difficulty=20)
    db.commit()

    scan_unset = scan_term_gaps(db, client_a)
    assert scan_unset.gaps == []
    assert scan_unset.summary["brand"] == 2

    client_a.primary_market = "Orlando, FL"
    db.commit()
    scan_other = scan_term_gaps(db, client_a)
    assert scan_other.gaps == []
    assert scan_other.summary["brand"] == 2

    client_a.primary_market = "Jackson, MS"
    db.commit()
    scan_market = scan_term_gaps(db, client_a)
    assert [g.term for g in scan_market.gaps] == ["jackson hvac"]
    assert scan_market.gaps[0].absent_words == ("jackson",)
    assert scan_market.summary["brand"] == 1


def test_tampa_bay_geo_emd_preserved_while_reviews_and_bay_rival_filtered(
    db, client_a, client_b
):
    electrical_pages = (
        ("panel-upgrade", "Electrical Panel Upgrades"),
        ("wiring", "Residential Wiring"),
        ("lighting", "Commercial Lighting Installation"),
        ("ev-charger", "EV Charger Installation"),
        ("surge-protection", "Whole Home Surge Protection"),
        ("generators", "Standby Generator Wiring"),
        ("troubleshooting", "Electrical Troubleshooting"),
        ("outlets", "GFCI Outlet Replacement"),
        ("inspections", "Electrical Safety Inspections"),
        ("ceiling-fans", "Ceiling Fan Installation"),
    )

    client_a.client_name = "Gulf Coast Electrical"
    client_a.domain = "gulf-coast-electrical.com"
    client_a.competitor_domains = ["tampa-bay-electrical.com"]
    for slug, title in electrical_pages:
        _page(db, client_a.id, slug, title=title)
    _term(db, client_a.id, "tampa bay electrical contractor", volume=450, difficulty=20)
    _term(db, client_a.id, "tampa bay electrical reviews", volume=300, difficulty=20)
    db.commit()

    scan_tampa = scan_term_gaps(db, client_a)
    assert [g.term for g in scan_tampa.gaps] == ["tampa bay electrical contractor"]
    assert scan_tampa.summary["brand"] == 1

    client_b.client_name = "Suncoast Electrical"
    client_b.domain = "suncoast-electrical.com"
    client_b.competitor_domains = ["bay-electrical.com"]
    for slug, title in electrical_pages:
        _page(db, client_b.id, slug, title=title)
    _term(db, client_b.id, "bay electrical", volume=450, difficulty=20)
    db.commit()

    scan_bay = scan_term_gaps(db, client_b)
    assert scan_bay.gaps == []
    assert scan_bay.summary["brand"] == 1


def test_multi_competitor_geo_suffix_collision_preserves_geo_emd_while_blocking_rival(
    db, client_a
):
    from app.services.page_signals import is_rival_navigational, rival_brand_term_groups

    electrical_pages = (
        ("panel-upgrade", "Electrical Panel Upgrades"),
        ("wiring", "Residential Wiring"),
        ("lighting", "Commercial Lighting Installation"),
        ("ev-charger", "EV Charger Installation"),
        ("surge-protection", "Whole Home Surge Protection"),
        ("generators", "Standby Generator Wiring"),
        ("troubleshooting", "Electrical Troubleshooting"),
        ("outlets", "GFCI Outlet Replacement"),
        ("inspections", "Electrical Safety Inspections"),
        ("ceiling-fans", "Ceiling Fan Installation"),
    )

    client_a.client_name = "Gulf Coast Electrical"
    client_a.domain = "gulf-coast-electrical.com"
    client_a.competitor_domains = ["tampa-bay-electrical.com", "bay-electrical.com"]
    for slug, title in electrical_pages:
        _page(db, client_a.id, slug, title=title)
    _term(db, client_a.id, "tampa bay electrical contractor", volume=450, difficulty=20)
    _term(db, client_a.id, "tampa bay electrical reviews", volume=300, difficulty=20)
    _term(db, client_a.id, "bay electrical", volume=450, difficulty=20)
    db.commit()

    scan = scan_term_gaps(db, client_a)
    assert [g.term for g in scan.gaps] == ["tampa bay electrical contractor"]
    assert scan.summary["brand"] == 2

    exact_rival, emd_rival = rival_brand_term_groups(
        db, client_a, extra_domains=("smith-tampa-bay-electrical.com",)
    )
    core_vocab = content_words(" ".join(title for _, title in electrical_pages))
    assert (
        is_rival_navigational(
            "smith tampa bay electrical",
            exact_terms=exact_rival,
            emd_terms=emd_rival,
            core_vocab=core_vocab,
        )
        is True
    )


def test_is_rival_navigational_preserves_hyphenated_and_framed_geo_phrases():
    from app.services.page_signals import _rival_domain_term_groups, is_rival_navigational

    core_vocab = content_words(
        "Electrical Panel Upgrades Residential Wiring Commercial Lighting EV Charger Surge Protection"
    )
    exact_tampa, emd_tampa = _rival_domain_term_groups(
        [
            "tampa-bay-electrical.com",
            "bay-electrical.com",
            "smith-tampa-bay-electrical.com",
        ]
    )
    for safe_tampa_query in (
        "Tampa-Bay Electrical Contractor",
        "Tampa--Bay Electrical Contractor",
        "Tampa - Bay Electrical Contractor",
        "Tampa__Bay Electrical Contractor",
    ):
        assert (
            is_rival_navigational(
                safe_tampa_query,
                exact_terms=exact_tampa,
                emd_terms=emd_tampa,
                core_vocab=core_vocab,
            )
            is False
        )
    for blocked in (
        "bay electrical",
        "bay-electrical",
        "bay electrical tampa bay",
        "smith tampa bay electrical",
        "Smith Tampa-Bay Electrical",
        "smith_tampa_bay_electrical",
        "Tampa-Bay Electrical Reviews",
        "tampa_bay_electrical_reviews",
        "tampa_bay_electrical reviews",
    ):
        assert (
            is_rival_navigational(
                blocked,
                exact_terms=exact_tampa,
                emd_terms=emd_tampa,
                core_vocab=core_vocab,
            )
            is True
        )

    exact_framed, emd_framed = _rival_domain_term_groups(
        ["west-electrical.com", "licensed-electrical.com"]
    )
    for safe_geo_query in ("west tampa bay electrical", "licensed tampa bay electrical"):
        assert (
            is_rival_navigational(
                safe_geo_query,
                exact_terms=exact_framed,
                emd_terms=emd_framed,
                core_vocab=core_vocab,
            )
            is False
        )
    for rival_query in ("west electrical", "licensed electrical"):
        assert (
            is_rival_navigational(
                rival_query,
                exact_terms=exact_framed,
                emd_terms=emd_framed,
                core_vocab=core_vocab,
            )
            is True
        )

    hvac_vocab = content_words("HVAC Contractor AC Repair Furnace Installation")
    exact_wdm, emd_wdm = _rival_domain_term_groups(
        ["des-moines-hvac.com", "west-des-moines-hvac.com"]
    )
    assert (
        is_rival_navigational(
            "west-des-moines hvac contractor",
            exact_terms=exact_wdm,
            emd_terms=emd_wdm,
            core_vocab=hvac_vocab,
        )
        is False
    )

    for safe_variant in (
        "tampa bay's electrical contractor",
        "tampa/bay electrical contractor",
        "tampa:bay electrical contractor",
        "tampa.bay electrical contractor",
    ):
        assert (
            is_rival_navigational(
                safe_variant,
                exact_terms=exact_tampa,
                emd_terms=emd_tampa,
                core_vocab=core_vocab,
            )
            is False
        )
    for blocked_variant in (
        "smith's tampa-bay electrical",
        "tampa-bay/electrical reviews",
        "tampa-bay: electrical reviews",
        "tampa-bay.electrical reviews",
    ):
        assert (
            is_rival_navigational(
                blocked_variant,
                exact_terms=exact_tampa,
                emd_terms=emd_tampa,
                core_vocab=core_vocab,
            )
            is True
        )

    ex_louis, em_louis = _rival_domain_term_groups(["louis-electrical.com"])
    assert (
        is_rival_navigational(
            "st. louis electrical contractor",
            exact_terms=ex_louis,
            emd_terms=em_louis,
            core_vocab=core_vocab,
        )
        is False
    )
    ex_st_louis, em_st_louis = _rival_domain_term_groups(["st-louis-electrical.com"])
    assert (
        is_rival_navigational(
            "st. louis electrical reviews",
            exact_terms=ex_st_louis,
            emd_terms=em_st_louis,
            core_vocab=core_vocab,
        )
        is True
    )

    ex_pete, em_pete = _rival_domain_term_groups(["petersburg-electrical.com"])
    assert (
        is_rival_navigational(
            "st. petersburg electrical contractor",
            exact_terms=ex_pete,
            emd_terms=em_pete,
            core_vocab=core_vocab,
        )
        is False
    )
    ex_st_pete, em_st_pete = _rival_domain_term_groups(["st-petersburg-electrical.com"])
    assert (
        is_rival_navigational(
            "st. petersburg electrical reviews",
            exact_terms=ex_st_pete,
            emd_terms=em_st_pete,
            core_vocab=core_vocab,
        )
        is True
    )

    ex_laud, em_laud = _rival_domain_term_groups(["lauderdale-electrical.com"])
    assert (
        is_rival_navigational(
            "ft. lauderdale electrical contractor",
            exact_terms=ex_laud,
            emd_terms=em_laud,
            core_vocab=core_vocab,
        )
        is False
    )
    ex_ft_laud, em_ft_laud = _rival_domain_term_groups(["ft-lauderdale-electrical.com"])
    assert (
        is_rival_navigational(
            "ft. lauderdale electrical contractor",
            exact_terms=ex_ft_laud,
            emd_terms=em_ft_laud,
            core_vocab=core_vocab,
        )
        is False
    )
    assert (
        is_rival_navigational(
            "ft. lauderdale electrical reviews",
            exact_terms=ex_ft_laud,
            emd_terms=em_ft_laud,
            core_vocab=core_vocab,
        )
        is True
    )
    assert (
        is_rival_navigational(
            "ft-lauderdale-electrical",
            exact_terms=ex_ft_laud,
            emd_terms=em_ft_laud,
            core_vocab=core_vocab,
        )
        is True
    )

    ex_worth, em_worth = _rival_domain_term_groups(["worth-electrical.com"])
    assert (
        is_rival_navigational(
            "ft. worth electrical contractor",
            exact_terms=ex_worth,
            emd_terms=em_worth,
            core_vocab=core_vocab,
        )
        is False
    )
    ex_ft_worth, em_ft_worth = _rival_domain_term_groups(["ft-worth-electrical.com"])
    ex_fort_worth, em_fort_worth = _rival_domain_term_groups(["fort-worth-electrical.com"])
    assert (
        is_rival_navigational(
            "ft. worth electrical contractor",
            exact_terms=ex_ft_worth,
            emd_terms=em_ft_worth,
            core_vocab=core_vocab,
        )
        is False
    )
    assert (
        is_rival_navigational(
            "ft. worth electrical reviews",
            exact_terms=ex_ft_worth,
            emd_terms=em_ft_worth,
            core_vocab=core_vocab,
        )
        is True
    )
    assert (
        is_rival_navigational(
            "ft. worth electrical reviews",
            exact_terms=ex_fort_worth,
            emd_terms=em_fort_worth,
            core_vocab=core_vocab,
        )
        is True
    )
    assert (
        is_rival_navigational(
            "fort worth electrical reviews",
            exact_terms=ex_ft_worth,
            emd_terms=em_ft_worth,
            core_vocab=core_vocab,
        )
        is True
    )
    assert (
        is_rival_navigational(
            "ft-worth-electrical",
            exact_terms=ex_ft_worth,
            emd_terms=em_ft_worth,
            core_vocab=core_vocab,
        )
        is True
    )

    plumbing_vocab = content_words("Plumbing Repair Drain Cleaning Water Heater Installation")
    ex_jones, em_jones = _rival_domain_term_groups(["jones-plumbing.com"])
    for jones_query in ("jones' plumbing", "jones’ plumbing", "jones's plumbing", "jones’s plumbing"):
        assert (
            is_rival_navigational(
                jones_query,
                exact_terms=ex_jones,
                emd_terms=em_jones,
                core_vocab=plumbing_vocab,
            )
            is True
        )


def test_scan_term_gaps_strips_geo_phrases_and_chrome_from_rival_core_vocab(db, client_a):
    from app.services.page_signals import rival_vocab_words

    assert rival_vocab_words("Tampa Bay, FL") == frozenset({"fl"})
    assert rival_vocab_words("Tampa Bay AC & Heating") == frozenset({"ac", "heat"})
    assert rival_vocab_words("Apopka, FL") == frozenset({"apopka", "fl"})
    assert rival_vocab_words("Tampa, FL") == frozenset({"tampa", "fl"})
    assert rival_vocab_words("/tampa-bay-electrical") == frozenset({"electrical"})

    client_a.client_name = "Suncoast HVAC"
    client_a.domain = "suncoast-hvac.com"
    client_a.primary_market = "Tampa Bay, FL"
    client_a.competitor_domains = ["tampa-bay-hvac.com", "bay-hvac.com"]
    for slug, title in (
        ("tampa-bay-ac-heating", "Tampa Bay AC & Heating"),
        ("furnace-repair", "Furnace Repair Services"),
        ("hvac-maintenance", "HVAC Maintenance Plans"),
        ("duct-cleaning", "Air Duct Cleaning"),
        ("air-conditioning-installation", "Air Conditioning Installation"),
        ("thermostat-upgrade", "Smart Thermostat Installation"),
        ("indoor-air-quality", "Indoor Air Quality Testing"),
        ("heat-pumps", "Heat Pump Systems"),
        ("boiler-service", "Boiler Service and Inspection"),
        ("commercial-hvac", "Commercial HVAC Systems"),
    ):
        _page(db, client_a.id, slug, title=title)
    _page(db, client_a.id, "about-us", title="About Us", headings=["bay hvac"])
    _term(db, client_a.id, "bay hvac service", volume=450, difficulty=20)
    _term(db, client_a.id, "tampa bay hvac contractor", volume=450, difficulty=20)
    db.commit()

    scan = scan_term_gaps(db, client_a)
    assert [g.term for g in scan.gaps] == ["tampa bay hvac contractor"]
    assert scan.summary["brand"] == 1


def test_scan_term_gaps_ft_lauderdale_primary_market_blocks_lauderdale_rival(db, client_a):
    from app.services.page_signals import rival_vocab_words

    assert rival_vocab_words("Ft. Lauderdale, FL") == frozenset({"fl"})
    assert rival_vocab_words("Ft. Worth, TX") == frozenset({"tx"})

    client_a.client_name = "Suncoast Electrical"
    client_a.domain = "suncoast-electrical.com"
    client_a.primary_market = "Ft. Lauderdale, FL"
    client_a.competitor_domains = ["lauderdale-electrical.com", "ft-lauderdale-electrical.com"]
    for slug, title in (
        ("ft-lauderdale-electrical", "Ft. Lauderdale Electrical"),
        ("panel-upgrade", "Electrical Panel Upgrades"),
        ("wiring", "Residential Wiring"),
        ("lighting", "Commercial Lighting Installation"),
        ("ev-charger", "EV Charger Installation"),
        ("surge-protection", "Whole Home Surge Protection"),
        ("generators", "Standby Generator Wiring"),
        ("troubleshooting", "Electrical Troubleshooting"),
        ("outlets", "GFCI Outlet Replacement"),
        ("inspections", "Electrical Safety Inspections"),
    ):
        _page(db, client_a.id, slug, title=title)
    _term(db, client_a.id, "lauderdale electrical", volume=450, difficulty=20)
    _term(db, client_a.id, "ft. lauderdale electrical contractor", volume=450, difficulty=20)
    db.commit()

    scan = scan_term_gaps(db, client_a)
    assert [g.term for g in scan.gaps] == ["ft. lauderdale electrical contractor"]
    assert scan.summary["brand"] == 1
