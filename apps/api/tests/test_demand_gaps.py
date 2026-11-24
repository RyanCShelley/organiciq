"""Demand the site is shown for and has no page about.

The tracked-term scan can only say the pages somebody thought of exist. This
reads Search Console instead, so it has to be as careful about what it
excludes as about what it finds.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.decisions.content_gaps import (
    MIN_DEMAND_IMPRESSIONS,
    DemandGap,
    c2_write_the_page_for_demand,
)
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.gsc import FactGscQueryPage
from app.models.seranking import (
    FactSerCompetitorKeyword,
    FactSerKeyword,
    FactSerKeywordMetric,
)
from app.services.content_gap_signals import MIN_CRAWLED_PAGES
from app.services.demand_gaps import (
    PRICING_LIMIT,
    demand_candidates,
    queries_to_price,
    scan_demand_gaps,
)

TODAY = date.today()
DAY = TODAY - timedelta(days=3)


def _page(db, client_id, slug, title):
    url = f"https://example.com/{slug}"
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(), client_id=client_id, source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=DAY, raw_url=url, normalized_url=url, status_code=200,
            indexable=True, word_count=800, inbound_internal_links=5,
            inbound_editorial_links=3, redirect_count=0, title=title, sections=[],
        )
    )
    return url


def _site(db, client):
    for i in range(MIN_CRAWLED_PAGES):
        _page(db, client.id, f"filler-{i}", f"Filler {i}")
    _page(db, client.id, "hvac-repair", "Furnace repair")
    db.commit()


def _shown(
    db,
    client,
    query,
    impressions,
    *,
    clicks=1,
    position=30,
    url="https://example.com/hvac-repair",
):
    db.add(
        FactGscQueryPage(
            id=uuid4(), client_id=client.id, date=DAY, query=query, raw_url=url,
            normalized_url=url, country="", device="", impressions=Decimal(impressions),
            clicks=Decimal(clicks), ctr=Decimal("0.01"), average_position=Decimal(position),
        )
    )
    db.commit()


def _price(db, client, keyword, volume=400, difficulty=20):
    db.add(
        FactSerKeywordMetric(
            id=uuid4(), client_id=client.id, keyword=keyword, source="us",
            volume=volume, difficulty=difficulty, data_found=True, fetched_at=DAY,
        )
    )
    db.commit()


def _terms(db, client):
    gaps, summary, blocked = demand_candidates(db, client, today=TODAY)
    return {g.term for g in gaps}, summary, blocked


def test_demand_with_no_page_about_it_is_a_candidate(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    terms, _, _ = _terms(db, client_a)
    assert terms == {"heat pump installation"}


def test_a_query_below_the_impression_floor_is_set_aside_and_counted(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", MIN_DEMAND_IMPRESSIONS - 1)
    terms, summary, _ = _terms(db, client_a)
    assert terms == set()
    assert summary["demand_small"] == 1


def test_a_tracked_query_is_not_demand_nobody_has_seen(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    db.add(
        FactSerKeyword(
            id=uuid4(), client_id=client_a.id, site_engine_id="1", keyword_id="k",
            keyword="Heat Pump Installation", volume=400,
        )
    )
    db.commit()
    terms, summary, _ = _terms(db, client_a)
    assert terms == set() and summary["demand_tracked"] == 1


def test_a_brand_query_is_navigation_not_demand(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, f"{client_a.client_name.lower()} reviews", 400)
    terms, summary, _ = _terms(db, client_a)
    assert terms == set() and summary["demand_brand"] == 1


def test_a_query_already_earning_its_page_is_left_alone(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400, position=4)
    terms, summary, _ = _terms(db, client_a)
    assert terms == set() and summary["demand_earning"] == 1


def test_a_query_a_page_is_about_is_a_refresh_not_a_new_page(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "furnace repair", 400)
    terms, summary, _ = _terms(db, client_a)
    assert terms == set() and summary["demand_covered"] == 1


def test_a_crawl_too_small_to_prove_absence_says_nothing(db, client_a):
    _page(db, client_a.id, "only", "Only page")
    db.commit()
    _shown(db, client_a, "heat pump installation", 400)
    gaps, _, blocked = demand_candidates(db, client_a, today=TODAY)
    assert gaps == [] and "too few" in blocked


def test_variants_are_one_page_led_by_the_biggest(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    _shown(db, client_a, "heat pump installation cost", 150)
    gaps, _, _ = demand_candidates(db, client_a, today=TODAY)
    assert [g.term for g in gaps] == ["heat pump installation"]
    assert gaps[0].also_covers == (("heat pump installation cost", 150.0),)


def test_an_unpriced_gap_is_not_prescribed_and_is_counted(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert scan.gaps == [] and scan.summary["demand_unpriced"] == 1


def test_a_priced_gap_is_prescribed_with_its_evidence(db, client_a):
    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    _price(db, client_a, "heat pump installation", volume=900, difficulty=30)
    scan = scan_demand_gaps(db, client_a, today=TODAY)
    found = c2_write_the_page_for_demand(scan.gaps[0])
    assert found.action_id == "C-2" and found.target_url == ""
    assert found.metric_key == "term_position"
    assert found.score == 900 * 0.7
    assert "400 times" in found.why and "900 searches a month" in found.why
    assert any("facts_gsc_query_pages" in line for line in found.evidence)


def test_a_price_below_the_volume_floor_is_not_prescribed():
    gap = DemandGap(term="x", impressions=500, clicks=0, position=40, volume=10, difficulty=5)
    assert c2_write_the_page_for_demand(gap) is None


def test_the_pricing_job_buys_the_largest_unpriced_once(db, client_a):
    _site(db, client_a)
    for i in range(PRICING_LIMIT + 5):
        _shown(db, client_a, f"zzz{i} widget", 1000 - i)
    _price(db, client_a, "zzz0 widget")
    wanted = queries_to_price(db, client_a, today=TODAY)
    assert len(wanted) == PRICING_LIMIT
    assert "zzz0 widget" not in wanted
    assert wanted[0] == "zzz1 widget"


def test_the_keyword_pricing_list_includes_demand(db, client_a):
    from app.ingestion.dataforseo.keyword_metrics import keywords_to_price

    _site(db, client_a)
    _shown(db, client_a, "heat pump installation", 400)
    assert keywords_to_price(db, client_a.id, today=TODAY) == ["heat pump installation"]


def test_an_untracked_term_is_judged_on_search_console_position(db, client_a):
    from app.services.results import _query_position

    _shown(db, client_a, "heat pump installation", 100, position=40)
    _shown(db, client_a, "heat pump installation", 300, position=20, url="https://example.com/other")
    # Impression-weighted, not a plain average of the two rows.
    assert _query_position(db, client_a.id, "Heat Pump Installation", TODAY).value == 25.0
    assert _query_position(db, client_a.id, "nothing", TODAY).value is None


# ── Irrelevance filtering & waiting guard fixtures ──


def _hvac_site(db, client):
    pages = [
        ("ac-repair", "AC Repair Services", ["Emergency AC Repair"]),
        ("furnace-repair", "Furnace Repair", ["Gas Furnace Troubleshooting"]),
        ("hvac-maintenance", "HVAC Maintenance Plans", ["Seasonal Tune-Up"]),
        ("duct-cleaning", "Air Duct Cleaning", ["Residential Ductwork"]),
        ("air-conditioning-installation", "Air Conditioning Installation", ["Central Air Units"]),
        ("thermostat-upgrade", "Smart Thermostat Installation", ["Programmable Thermostats"]),
        ("indoor-air-quality", "Indoor Air Quality Testing", ["HEPA Filtration"]),
        ("heat-pumps", "Heat Pump Systems", ["Cold Climate Heat Pumps"]),
        ("boiler-service", "Boiler Service and Inspection", ["Hydronic Heating"]),
        ("commercial-hvac", "Commercial HVAC Contractors", ["Rooftop Units"]),
    ]
    for slug, title, headings in pages:
        url = f"https://example.com/{slug}"
        db.add(
            FactCrawlPageSnapshot(
                id=uuid4(),
                client_id=client.id,
                source=CRAWL_SOURCE_FIRST_PARTY,
                snapshot_date=DAY,
                raw_url=url,
                normalized_url=url,
                status_code=200,
                indexable=True,
                word_count=900,
                inbound_internal_links=5,
                inbound_editorial_links=3,
                redirect_count=0,
                title=title,
                description="Residential and commercial heating and cooling repair.",
                faq_questions=["How often should you schedule a tune up?"],
                sections=[{"heading": h, "first_paragraph": "Certified technicians."} for h in headings],
            )
        )
    client.competitor_domains = ["rivalhvac.com", "ibm.com"]
    db.commit()


def _rival_rank(db, client, domain, keyword, *, position=3, volume=800, difficulty=30):
    db.add(
        FactSerCompetitorKeyword(
            id=uuid4(),
            client_id=client.id,
            competitor_domain=domain,
            keyword=keyword,
            position=Decimal(position),
            volume=Decimal(volume),
            difficulty=Decimal(difficulty),
            fetched_at=DAY,
        )
    )
    db.commit()


def test_hvac_relevant_gsc_competitor_and_faq_watchlist_gaps_are_kept(db, client_a):
    from app.models.watchlist import WatchlistBucket, WatchlistKeyword

    _hvac_site(db, client_a)
    bucket = WatchlistBucket(
        client_id=client_a.id, name="Geothermal Heating", name_key="geothermal heating", sort_order=0
    )
    db.add(bucket)
    db.flush()
    db.add(
        WatchlistKeyword(
            client_id=client_a.id,
            bucket_id=bucket.id,
            keyword="geothermal loop inspection",
            keyword_key="geothermal loop inspection",
            source="csv",
        )
    )
    db.commit()

    # Relevant GSC gap with absent geo modifier ("orlando")
    _shown(db, client_a, "heat pump rebate orlando", 350, position=22)
    _price(db, client_a, "heat pump rebate orlando", volume=600, difficulty=25)
    # Relevant GSC gap matching via WatchlistKeyword ("geothermal")
    _shown(db, client_a, "geothermal troubleshooting", 260, position=18)
    # Relevant competitor gap with absent modifier ("ductless")
    _rival_rank(db, client_a, "rivalhvac.com", "ductless heat pump installation", position=2, volume=900, difficulty=28)

    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert {g.term for g in scan.gaps} == {
        "heat pump rebate orlando",
        "ductless heat pump installation",
    }
    assert {g.term for g in scan.unpriced} == {"geothermal troubleshooting"}
    assert queries_to_price(db, client_a, today=TODAY) == ["geothermal troubleshooting"]


def test_off_topic_gsc_and_competitor_queries_are_filtered(db, client_a):
    _hvac_site(db, client_a)
    _shown(db, client_a, "minecraft server hosting", 500, position=24)
    _price(db, client_a, "minecraft server hosting", volume=5000, difficulty=15)
    _shown(db, client_a, "car insurance cost", 300, position=20)
    _price(db, client_a, "car insurance cost", volume=3000, difficulty=30)
    _rival_rank(db, client_a, "rivalhvac.com", "best pizza near me", position=2, volume=4000, difficulty=20)
    _rival_rank(db, client_a, "rivalhvac.com", "free dog training tips", position=4, volume=2000, difficulty=20)

    candidates, demand_summary, _ = demand_candidates(db, client_a, today=TODAY)
    assert candidates == []
    assert demand_summary["demand_off_topic"] == 2
    assert queries_to_price(db, client_a, today=TODAY) == []

    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert scan.gaps == []
    assert scan.summary["competitor_off_topic"] == 2


def test_navigational_utility_and_platform_queries_filtered_while_b2b_passes(db, client_a):
    _hvac_site(db, client_a)
    for bad in (
        "customer portal login",
        "hvac technician jobs",
        "furnace repair careers",
        "hvac tech salary",
        "furnace manual pdf download",
        "customer support phone number",
        "https://other-vendor.com/contact",
        "reddit hvac advice",
        "youtube furnace repair",
        "chatgpt login",
    ):
        _shown(db, client_a, bad, 350, position=25)
    _rival_rank(db, client_a, "rivalhvac.com", "hubspot pricing", position=2, volume=3000, difficulty=25)
    _rival_rank(db, client_a, "rivalhvac.com", "hvac service by zip code", position=3, volume=700, difficulty=25)
    # Legitimate B2B phrases must pass noise filter (site mentions IT / passwords without full coverage)
    _page(db, client_a.id, "it-consulting", "IT Consulting")
    _page(db, client_a.id, "password-vault", "Password Security Vault")
    db.commit()
    _shown(db, client_a, "managed it support", 320, position=24)
    _shown(db, client_a, "password manager", 310, position=26)

    candidates, summary, _ = demand_candidates(db, client_a, today=TODAY)
    assert {g.term for g in candidates} == {"managed it support", "password manager"}
    assert summary["demand_noise"] == 10

    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert {g.term for g in scan.gaps} == {"hvac service by zip code"}
    assert scan.summary["competitor_noise"] == 1


def test_short_brand_and_rival_brand_filtering_without_false_matches(db, client_a):
    from app.models.llm_visibility import ClientLlmSettings

    client_a.client_name = "SMA"
    client_a.domain = "sma.com"
    _hvac_site(db, client_a)
    db.add(
        ClientLlmSettings(
            id=uuid4(),
            client_id=client_a.id,
            brand_name="SMA Cooling",
            brand_patterns=["sma pros"],
            competitors={"acme-air.com": {"name": "Acme Air", "patterns": ["acme hvac"]}},
        )
    )
    db.commit()

    # Should be filtered as brand / rival brand
    for brand_q in (
        "sma reviews",
        "sma's pricing",
        "sma pros hvac",
        "rivalhvac furnace repair",
        "ibm thermostat",
        "acme hvac maintenance",
    ):
        _shown(db, client_a, brand_q, 300, position=22)
    _rival_rank(db, client_a, "ibm.com", "ibm smart furnace", position=2, volume=900, difficulty=20)
    # Must NOT be false-matched by "sma" substring
    _shown(db, client_a, "small business furnace rebate", 320, position=22)

    candidates, summary, _ = demand_candidates(db, client_a, today=TODAY)
    assert [g.term for g in candidates] == ["small business furnace rebate"]
    assert summary["demand_brand"] == 6

    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert scan.gaps == []
    assert scan.summary["competitor_brand"] == 1


def test_two_char_domain_does_not_block_it_services(db, client_a):
    client_a.client_name = "IT"
    client_a.domain = "it.com"
    _site(db, client_a)
    _shown(db, client_a, "it services", 300, position=22)
    _shown(db, client_a, "it.com reviews", 300, position=22)
    terms, summary, _ = _terms(db, client_a)
    assert terms == {"it services"}
    assert summary["demand_brand"] == 1


def test_watch_target_excluded_suppresses_gsc_competitor_and_pricing(db, client_a):
    from app.models.watch_target import WatchTarget

    _hvac_site(db, client_a)
    db.add(
        WatchTarget(
            id=uuid4(),
            client_id=client_a.id,
            kind="keyword",
            item_key="k-excluded",
            text="  Radiant   Floor   Heating ",
            state="excluded",
        )
    )
    db.commit()

    _shown(db, client_a, "radiant floor heating", 400, position=20)
    _price(db, client_a, "radiant floor heating", volume=900, difficulty=20)
    _rival_rank(db, client_a, "rivalhvac.com", "radiant floor heating", position=2, volume=900, difficulty=20)
    _shown(db, client_a, "radiant floor heating cost", 250, position=24)

    # Exact excluded normalized term suppressed across GSC, competitor, and pricing;
    # non-excluded query still priced.
    _rival_rank(db, client_a, "rivalhvac.com", "hydronic heating installation orlando", position=3, volume=600, difficulty=25)
    assert queries_to_price(db, client_a, today=TODAY) == ["radiant floor heating cost"]
    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert [g.term for g in scan.gaps] == ["hydronic heating installation orlando"]
    assert scan.summary["demand_excluded"] == 1


def test_unpriced_waiting_guard_filters_rejected_metrics_low_signal_variants_and_caps_at_20(
    db, client_a
):
    from app.services import content_gaps_view

    _hvac_site(db, client_a)
    # 1. Priced lead gap (with a folded variant in also_covers) + competitor-priced superset
    _shown(db, client_a, "heat pump tune up", 450, position=22)
    _price(db, client_a, "heat pump tune up", volume=800, difficulty=25)
    # Unpriced variant overlapping priced lead gap -> must NOT reappear in waiting
    _shown(db, client_a, "heat pump tune up checklist", 350, position=24)
    _rival_rank(
        db,
        client_a,
        "rivalhvac.com",
        "commercial heat pump installation",
        position=2,
        volume=900,
        difficulty=25,
    )
    _shown(db, client_a, "heat pump installation", 350, position=24)

    # 2. Metrics already checked & rejected by DataForSEO -> must NOT appear in waiting
    _shown(db, client_a, "furnace blower replacement", 350, position=24)
    db.add(
        FactSerKeywordMetric(
            id=uuid4(),
            client_id=client_a.id,
            keyword="furnace blower replacement",
            source="us",
            volume=500,
            difficulty=20,
            data_found=False,
            fetched_at=DAY,
        )
    )
    _shown(db, client_a, "ac coil inspection", 350, position=24)
    _price(db, client_a, "ac coil inspection", volume=0, difficulty=20)
    _shown(db, client_a, "duct damper adjustment", 350, position=24)
    _price(db, client_a, "duct damper adjustment", volume=30, difficulty=20)
    _shown(db, client_a, "boiler pressure gauge", 350, position=24)
    _price(db, client_a, "boiler pressure gauge", volume=400, difficulty=None)

    # 3. Low-signal unpriced GSC queries -> must NOT appear in waiting
    _shown(db, client_a, "hvac filter schedule", 150, position=20)  # < 200 imp
    _shown(db, client_a, "furnace igniter cost", 300, position=65)   # > 50 pos
    _shown(db, client_a, "thermostat", 300, position=20)             # 1 word, 1 click

    # 4. 25 legitimate eligible unpriced queries -> capped at 20, highest impressions first
    for i in range(25):
        _shown(db, client_a, f"hvac zone {i} repair", 210 + i, position=25)
    db.commit()

    view = content_gaps_view.build(db, client_a)
    waiting = [g for g in view["gaps"] if not g["priced"]]
    waiting_terms = [g["term"] for g in waiting]
    assert len(waiting) == content_gaps_view.WAITING_LIMIT == 20
    assert waiting_terms[0] == "hvac zone 24 repair"
    assert waiting_terms[-1] == "hvac zone 5 repair"
    for rejected in (
        "heat pump tune up checklist",
        "heat pump installation",
        "furnace blower replacement",
        "ac coil inspection",
        "duct damper adjustment",
        "boiler pressure gauge",
        "hvac filter schedule",
        "furnace igniter cost",
        "thermostat",
    ):
        assert rejected not in {g["term"] for g in view["gaps"]}


def test_v2_content_gaps_end_to_end_filters_irrelevant_and_preserves_counts(
    client, db, client_a, admin_user
):
    from app.models.watch_target import WatchTarget
    from tests.conftest import client_header

    client_a.client_name = "SMA"
    client_a.domain = "sma.com"
    _hvac_site(db, client_a)
    db.add(
        WatchTarget(
            id=uuid4(),
            client_id=client_a.id,
            kind="keyword",
            item_key="k-ex",
            text="boiler leak",
            state="excluded",
        )
    )

    # Relevant gaps (1 GSC priced, 1 GSC unpriced waiting, 1 competitor, 1 watchlist)
    _shown(db, client_a, "heat pump rebate orlando", 350, position=22)
    _price(db, client_a, "heat pump rebate orlando", volume=700, difficulty=25)
    _shown(db, client_a, "furnace safety inspection", 300, position=24)
    _rival_rank(db, client_a, "rivalhvac.com", "mini split ac repair", position=3, volume=800, difficulty=20)
    db.add(
        FactSerKeyword(
            id=uuid4(),
            client_id=client_a.id,
            site_engine_id="1",
            keyword_id="w1",
            keyword="commercial hvac energy audit",
            volume=500,
        )
    )
    _price(db, client_a, "commercial hvac energy audit", volume=500, difficulty=20)

    # Irrelevant noise across all sources
    _shown(db, client_a, "minecraft server hosting", 600, position=20)
    _price(db, client_a, "minecraft server hosting", volume=5000, difficulty=10)
    _shown(db, client_a, "sma reviews", 500, position=18)
    _shown(db, client_a, "boiler leak", 400, position=20)
    _shown(db, client_a, "customer portal login", 400, position=25)
    _rival_rank(db, client_a, "rivalhvac.com", "best pizza near me", position=1, volume=9000, difficulty=10)
    _rival_rank(db, client_a, "rivalhvac.com", "rivalhvac login", position=1, volume=2000, difficulty=10)
    db.commit()

    resp = client.get("/v2/content/gaps", headers=client_header(client_a.id, admin_user.email))
    assert resp.status_code == 200
    data = resp.json()
    terms = [g["term"] for g in data["gaps"]]
    assert set(terms) == {
        "heat pump rebate orlando",
        "mini split ac repair",
        "commercial hvac energy audit",
        "furnace safety inspection",
    }
    assert terms[-1] == "furnace safety inspection"
    assert data["counts"]["gaps"] == 4
    assert data["counts"]["searched"] == 2
    assert data["counts"]["competitor"] == 1
    assert data["counts"]["watchlist"] == 1


def test_descriptive_industry_client_and_rival_names_preserve_industry_queries(db, client_a):
    from app.models.llm_visibility import ClientLlmSettings

    # Case A: Smith HVAC / jones-hvac.com / orlando-cooling.com
    _hvac_site(db, client_a)
    client_a.client_name = "Smith HVAC"
    client_a.domain = "smith-hvac.com"
    client_a.competitor_domains = ["jones-hvac.com", "orlando-cooling.com"]
    db.add(
        ClientLlmSettings(
            id=uuid4(),
            client_id=client_a.id,
            brand_name="SMA Cooling",
            brand_patterns=["smith hvac"],
            competitors={"acme-hvac.com": {"name": "Acme HVAC", "patterns": ["acme cooling"]}},
        )
    )
    db.commit()

    _shown(db, client_a, "hvac maintenance checklist", 500, position=18)
    _shown(db, client_a, "cooling rebates orlando", 420, position=20)
    _shown(db, client_a, "smith hvac login", 400, position=18)
    _rival_rank(db, client_a, "jones-hvac.com", "hvac inspection cost", position=3, volume=400, difficulty=20)
    _rival_rank(db, client_a, "jones-hvac.com", "jones hvac reviews", position=2, volume=500, difficulty=20)

    candidates, summary, _ = demand_candidates(db, client_a, today=TODAY)
    assert {g.term for g in candidates} == {"hvac maintenance checklist", "cooling rebates orlando"}
    assert summary["demand_brand"] == 1
    assert summary["demand_off_topic"] == 0
    assert sorted(queries_to_price(db, client_a, today=TODAY)) == [
        "cooling rebates orlando",
        "hvac maintenance checklist",
    ]

    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert [g.term for g in scan.gaps] == ["hvac inspection cost"]
    assert scan.summary["competitor_brand"] == 1
    assert scan.summary["competitor_off_topic"] == 0


def test_boys_electrical_and_aquaman_and_sma_marketing_keep_core_industry_queries(db, client_a):
    # Boys Electrical
    client_a.client_name = "Boys Electrical"
    client_a.domain = "boys-electrical.com"
    client_a.competitor_domains = ["orlando-electrical.com"]
    electrical_pages = [
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
    ]
    for slug, title in electrical_pages:
        _page(db, client_a.id, slug, title)
    db.commit()

    _shown(db, client_a, "electrical contractor", 450, position=22)
    _shown(db, client_a, "electrical permit orlando", 380, position=24)
    _shown(db, client_a, "boys electrical pricing", 350, position=20)
    _shown(db, client_a, "orlando electrical reviews", 340, position=20)
    candidates, summary, _ = demand_candidates(db, client_a, today=TODAY)
    assert {g.term for g in candidates} == {"electrical contractor", "electrical permit orlando"}
    assert summary["demand_brand"] == 2

    # Aquaman Pool Leak Detection (new client)
    from app.models.client import Client

    pool_client = Client(
        id=uuid4(),
        tier_id=client_a.tier_id,
        client_name="Aquaman Pool Leak Detection",
        slug="aquaman-pool-leak-test",
        domain="aquamanpools.com",
        competitor_domains=["orlando-pool-repair.com"],
    )
    db.add(pool_client)
    db.flush()
    for i, (slug, title) in enumerate(
        [
            ("pool-leak", "Swimming Pool Leak Detection"),
            ("spa-leak", "Hot Tub and Spa Leak Repair"),
            ("vinyl-liner", "Vinyl Liner Leak Testing"),
            ("skimmer-repair", "Pool Skimmer Crack Repair"),
            ("main-drain", "Main Drain Pressure Testing"),
            ("dye-test", "Pool Dye Testing Services"),
            ("plumbing-leak", "Underground Pool Plumbing Repair"),
            ("gunite-crack", "Gunite Pool Crack Sealing"),
            ("deck-sealing", "Pool Deck Pipe Inspection"),
            ("acoustic-leak", "Acoustic Pool Leak Listening"),
        ]
    ):
        _page(db, pool_client.id, slug, title)
    db.commit()
    _shown(db, pool_client, "pool leak detection cost", 420, position=22)
    _shown(db, pool_client, "aquaman pool leak detection reviews", 300, position=18)
    pool_cands, pool_sum, _ = demand_candidates(db, pool_client, today=TODAY)
    assert [g.term for g in pool_cands] == ["pool leak detection cost"]
    assert pool_sum["demand_brand"] == 1

    # SMA Marketing
    sma_client = Client(
        id=uuid4(),
        tier_id=client_a.tier_id,
        client_name="SMA Marketing",
        slug="sma-marketing-test",
        domain="smamarketing.com",
    )
    db.add(sma_client)
    db.flush()
    for slug, title in [
        ("seo", "Enterprise SEO Services"),
        ("content-marketing", "Content Marketing Strategy"),
        ("technical-seo", "Technical SEO Audits"),
        ("link-building", "Link Building Campaigns"),
        ("local-seo", "Local Search Marketing"),
        ("cro", "Conversion Rate Optimization"),
        ("analytics", "Marketing Analytics Setup"),
        ("paid-search", "Paid Search Management"),
        ("email-marketing", "Email Marketing Automation"),
        ("hubspot-ops", "Marketing Operations"),
    ]:
        _page(db, sma_client.id, slug, title)
    db.commit()
    _shown(db, sma_client, "b2b marketing guide", 380, position=22)
    _shown(db, sma_client, "sma marketing reviews", 300, position=18)
    sma_cands, sma_sum, _ = demand_candidates(db, sma_client, today=TODAY)
    assert [g.term for g in sma_cands] == ["b2b marketing guide"]
    assert sma_sum["demand_brand"] == 1


def test_utility_boilerplate_and_descriptions_do_not_pollute_vocab_or_unlock_platforms(db, client_a):
    _hvac_site(db, client_a)
    # Add utility / chrome pages with off-topic descriptions & first_paragraphs,
    # plus a substantive page whose description mentions YouTube.
    for slug, title, desc, fp, page_type in (
        (
            "careers",
            "Careers",
            "Join our team with health insurance and paid vacation benefits.",
            "Apply for full-time technician roles today.",
            "informational",
        ),
        (
            "privacy-policy",
            "Privacy Policy",
            "How we handle credit card data and cookies.",
            "California residents privacy notice.",
            "utility",
        ),
        (
            "about",
            "About Us",
            "We love baseball and pizza on Fridays.",
            "Subscribe on YouTube for HVAC tips and better results.",
            "informational",
        ),
        (
            "legal-notice",
            "Legal Notice",
            "Terms and legal notices for baseball fans.",
            "YouTube channel disclosures.",
            "utility",
        ),
    ):
        url = f"https://example.com/{slug}"
        db.add(
            FactCrawlPageSnapshot(
                id=uuid4(),
                client_id=client_a.id,
                source=CRAWL_SOURCE_FIRST_PARTY,
                snapshot_date=DAY,
                raw_url=url,
                normalized_url=url,
                status_code=200,
                indexable=True,
                word_count=500,
                inbound_internal_links=3,
                inbound_editorial_links=1,
                redirect_count=0,
                page_type=page_type,
                title=title,
                description=desc,
                sections=[{"heading": title, "first_paragraph": fp}],
            )
        )
    # Substantive page whose description (NOT title/path/heading) mentions YouTube
    url_sub = "https://example.com/duct-sealing"
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(),
            client_id=client_a.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=DAY,
            raw_url=url_sub,
            normalized_url=url_sub,
            status_code=200,
            indexable=True,
            word_count=700,
            inbound_internal_links=4,
            inbound_editorial_links=2,
            redirect_count=0,
            title="Aeroseal Duct Sealing",
            description="Subscribe on YouTube for HVAC tips.",
            sections=[{"heading": "Duct Sealing", "first_paragraph": "Better air flow."}],
        )
    )
    db.commit()

    for off_topic in (
        "car insurance quote",
        "credit card rewards",
        "best pizza near me",
        "baseball batting cages",
        "paid vacation packages",
        "iphone repair",
        "carpet cleaning",
        "solar panel installation",
        "better comparison guide",
    ):
        _shown(db, client_a, off_topic, 350, position=22)
        _rival_rank(db, client_a, "rivalhvac.com", off_topic, position=2, volume=900, difficulty=20)
    for platform_noise in ("youtube cooking videos", "youtube hvac"):
        _shown(db, client_a, platform_noise, 350, position=22)
        _rival_rank(db, client_a, "rivalhvac.com", platform_noise, position=2, volume=900, difficulty=20)

    _shown(db, client_a, "heat pump rebate orlando", 350, position=22)

    candidates, summary, _ = demand_candidates(db, client_a, today=TODAY)
    assert [g.term for g in candidates] == ["heat pump rebate orlando"]
    assert summary["demand_off_topic"] == 9
    assert summary["demand_noise"] == 2

    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert scan.gaps == []
    assert scan.summary["competitor_off_topic"] == 9
    assert scan.summary["competitor_noise"] == 2


def test_boilerplate_only_crawl_with_single_topic_keeps_industry_queries(db, client_a):
    from app.models.config import Topic, TopicStatus

    boilerplate_pages = [
        ("", "Home"),
        ("about-us", "About Us"),
        ("contact-us", "Contact Us"),
        ("our-team", "Our Team"),
        ("photo-gallery", "Photo Gallery"),
        ("testimonials", "Client Testimonials"),
        ("locations", "Service Areas & Locations"),
        ("request-a-quote", "Request a Quote"),
        ("careers", "Careers"),
        ("privacy-policy", "Privacy Policy"),
    ]
    for slug, title in boilerplate_pages:
        url = f"https://example.com/{slug}" if slug else "https://example.com/"
        db.add(
            FactCrawlPageSnapshot(
                id=uuid4(),
                client_id=client_a.id,
                source=CRAWL_SOURCE_FIRST_PARTY,
                snapshot_date=DAY,
                raw_url=url,
                normalized_url=url,
                status_code=200,
                indexable=True,
                word_count=400,
                inbound_internal_links=5,
                inbound_editorial_links=2,
                redirect_count=0,
                title=title,
                sections=[{"heading": title}],
            )
        )
    db.add(
        Topic(
            id=uuid4(),
            client_id=client_a.id,
            topic_name="HVAC",
            status=TopicStatus.ACTIVE,
        )
    )
    db.commit()

    for q in ("heat pump installation", "furnace repair", "duct cleaning"):
        _shown(db, client_a, q, 350, position=22)

    candidates, summary, _ = demand_candidates(db, client_a, today=TODAY)
    assert {g.term for g in candidates} == {
        "heat pump installation",
        "furnace repair",
        "duct cleaning",
    }
    assert summary["demand_off_topic"] == 0


def test_waiting_dedup_suppresses_also_covers_and_tracked_gap_variants(db, client_a):
    from app.services import content_gaps_view

    _hvac_site(db, client_a)
    # 1. Competitor lead "commercial ductless heat pump" folds "ductless heat pump" into also_covers.
    #    Note: "ductless heat pump cost" does NOT subset/superset "commercial ductless heat pump"
    #    ("cost" vs "commercial"), so it is suppressed ONLY via also_covers!
    _rival_rank(
        db,
        client_a,
        "rivalhvac.com",
        "commercial ductless heat pump",
        position=2,
        volume=1000,
        difficulty=25,
    )
    _rival_rank(
        db,
        client_a,
        "rivalhvac.com",
        "ductless heat pump",
        position=3,
        volume=600,
        difficulty=25,
    )
    # Unpriced variant of also_covers -> must NOT leak into waiting
    _shown(db, client_a, "ductless heat pump cost", 350, position=24)

    # 2. Watchlist tracked gap + unpriced variant -> variant must NOT leak into waiting
    db.add(
        FactSerKeyword(
            id=uuid4(),
            client_id=client_a.id,
            site_engine_id="1",
            keyword_id="w-geo",
            keyword="geothermal heating repair",
            volume=500,
        )
    )
    _price(db, client_a, "geothermal heating repair", volume=500, difficulty=20)
    _shown(db, client_a, "geothermal heating repair cost", 340, position=24)

    # 3. Distinct unpriced waiting query -> SHOULD appear in waiting
    _shown(db, client_a, "hydronic radiant floor", 320, position=24)
    db.commit()

    view = content_gaps_view.build(db, client_a)
    terms = {g["term"] for g in view["gaps"]}
    assert {
        "commercial ductless heat pump",
        "geothermal heating repair",
        "hydronic radiant floor",
    } <= terms
    assert "ductless heat pump cost" not in terms
    assert "geothermal heating repair cost" not in terms


def test_watch_target_excluded_punctuation_variants_and_gsc_multispaces(db, client_a):
    from app.models.watch_target import WatchTarget
    from app.services import content_gaps_view

    _hvac_site(db, client_a)
    db.add(
        WatchTarget(
            id=uuid4(),
            client_id=client_a.id,
            kind="keyword",
            item_key="k-hp-sizing",
            text="heat-pump sizing",
            state="excluded",
        )
    )
    db.add(
        WatchTarget(
            id=uuid4(),
            client_id=client_a.id,
            kind="keyword",
            item_key="k-furnace-cost",
            text="furnace installation cost?",
            state="excluded",
        )
    )
    db.commit()

    _shown(db, client_a, "heat pump sizing", 400, position=20)
    _shown(db, client_a, "furnace installation cost", 350, position=22)
    _shown(db, client_a, "boiler efficiency inspection", 300, position=24)
    _rival_rank(db, client_a, "rivalhvac.com", "heat pump sizing", position=2, volume=700, difficulty=20)
    _rival_rank(db, client_a, "rivalhvac.com", "furnace installation cost", position=3, volume=600, difficulty=20)

    # GSC query (< MIN_DEMAND_IMPRESSIONS so competitor_candidates looks it up)
    # with internal multi-spaces matching competitor keyword.
    _shown(db, client_a, "geothermal   heat   pump   repair", 50, position=22)
    _rival_rank(
        db,
        client_a,
        "rivalhvac.com",
        "geothermal heat pump repair",
        position=3,
        volume=650,
        difficulty=24,
    )

    assert queries_to_price(db, client_a, today=TODAY) == ["boiler efficiency inspection"]
    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert [g.term for g in scan.gaps] == ["geothermal heat pump repair"]
    assert scan.gaps[0].impressions == 50.0
    assert scan.summary["demand_excluded"] == 2
    assert scan.summary["competitor_excluded"] == 2

    view = content_gaps_view.build(db, client_a)
    assert {g["term"] for g in view["gaps"]} == {
        "geothermal heat pump repair",
        "boiler efficiency inspection",
    }
    geo_row = next(g for g in view["gaps"] if g["term"] == "geothermal heat pump repair")
    assert geo_row["impressions"] == 50


def test_scan_demand_gaps_promotes_priced_variant_under_unpriced_lead(db, client_a):
    from app.services import content_gaps_view

    _hvac_site(db, client_a)
    # Higher-impression unpriced GSC query folds a lower-impression priced variant.
    _shown(db, client_a, "heat pump rebate", 500, position=22)
    _shown(db, client_a, "heat pump rebate orlando", 250, position=24)
    _price(db, client_a, "heat pump rebate orlando", volume=800, difficulty=20)
    # Also verify rejected lead metric does not block a qualifying priced variant.
    _shown(db, client_a, "boiler inspection checklist", 450, position=25)
    db.add(
        FactSerKeywordMetric(
            id=uuid4(),
            client_id=client_a.id,
            keyword="boiler inspection checklist",
            source="us",
            volume=500,
            difficulty=20,
            data_found=False,
            fetched_at=DAY,
        )
    )
    _shown(db, client_a, "boiler inspection checklist orlando", 150, position=26)
    _price(db, client_a, "boiler inspection checklist orlando", volume=500, difficulty=20)
    db.commit()

    candidates, _, _ = demand_candidates(db, client_a, today=TODAY)
    assert {g.term for g in candidates} == {"heat pump rebate", "boiler inspection checklist"}

    scan = scan_demand_gaps(db, client_a, today=TODAY)
    by_term = {g.term: g for g in scan.gaps}
    assert set(by_term) == {"heat pump rebate orlando", "boiler inspection checklist orlando"}
    hp = by_term["heat pump rebate orlando"]
    assert hp.priced is True
    assert hp.opportunity == 640.0
    assert hp.impressions == 250.0
    assert hp.also_covers == (("heat pump rebate", 500.0),)
    assert scan.unpriced == ()
    assert scan.summary["demand_unpriced"] == 0

    view = content_gaps_view.build(db, client_a)
    view_by_term = {g["term"]: g for g in view["gaps"]}
    assert view_by_term["heat pump rebate orlando"]["priced"] is True
    assert view_by_term["heat pump rebate orlando"]["opportunity"] == 640
    assert "heat pump rebate" not in view_by_term


def test_scan_demand_gaps_skips_folded_variants_in_competitor_candidates(db, client_a):
    _hvac_site(db, client_a)
    _shown(db, client_a, "geothermal heat pump", 500, position=22)
    _price(db, client_a, "geothermal heat pump", volume=1000, difficulty=25)
    _shown(db, client_a, "geothermal heat pump guide", 200, position=24)
    _rival_rank(
        db,
        client_a,
        "rivalhvac.com",
        "geothermal heat pump guide",
        position=3,
        volume=600,
        difficulty=20,
    )
    db.commit()

    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert [g.term for g in scan.gaps] == ["geothermal heat pump"]
    assert scan.gaps[0].also_covers == (("geothermal heat pump guide", 200.0),)


def test_is_substantive_page_rejects_nested_suffixed_chrome_and_branded_home(db, client_a):
    from types import SimpleNamespace
    from app.services.demand_gaps import _is_substantive_page

    for url, title in (
        ("https://example.com/company/about-us", "About Our Company"),
        ("https://example.com/en/careers-orlando", "Join Our Team"),
        ("https://example.com/about-us.html", "Who We Are"),
        ("https://example.com/contact-us/", "Get In Touch"),
        ("https://example.com/privacy-policy/", "Legal"),
        ("https://example.com/terms-of-service/", "Service Rules"),
        ("https://example.com/", "Acme HVAC | Home"),
        ("https://example.com/", "Home - Acme HVAC"),
        ("https://example.com/index.html", "Acme HVAC | Home"),
        ("https://example.com/index.htm", "Home - Acme HVAC"),
        ("https://example.com/index.php", "Acme HVAC — Homepage"),
        ("https://example.com/index.php", ""),
        ("https://example.com/home", "Home-Based Care"),
    ):
        assert _is_substantive_page(url, SimpleNamespace(page_type="informational", title=title)) is False

    for url, title in (
        ("https://example.com/locations/orlando-ac-repair", "Orlando AC Repair"),
        ("https://example.com/blog/about-heat-pumps", "About Heat Pumps"),
        ("https://example.com/services/ac-repair.html", "AC Repair | Request a Quote"),
        ("https://example.com/", "Residential HVAC Services | Acme HVAC"),
        ("https://example.com/index.html", "Residential HVAC Services | Acme HVAC"),
        ("https://example.com/", "Home-Based HVAC Consulting | Acme"),
        ("https://example.com/index.php", "Home-Based HVAC Consulting | Acme"),
        ("https://example.com/blog/index.html", "HVAC Maintenance Blog"),
    ):
        assert _is_substantive_page(url, SimpleNamespace(page_type="informational", title=title)) is True

    _hvac_site(db, client_a)
    for url, title, desc in (
        ("https://example.com/company/about-us", "About Our Company", "Our dental insurance plan and pizza parties."),
        ("https://example.com/en/careers-orlando", "Join Our Team", "Great baseball perks and dental insurance."),
        ("https://example.com/about-us.html", "Who We Are", "Free pizza Fridays."),
        ("https://example.com/", "Acme HVAC | Home", "Best car insurance partner."),
    ):
        db.add(
            FactCrawlPageSnapshot(
                id=uuid4(),
                client_id=client_a.id,
                source=CRAWL_SOURCE_FIRST_PARTY,
                snapshot_date=DAY,
                raw_url=url,
                normalized_url=url,
                status_code=200,
                indexable=True,
                word_count=500,
                inbound_internal_links=3,
                inbound_editorial_links=1,
                redirect_count=0,
                page_type="informational",
                title=title,
                description=desc,
                sections=[{"heading": title}],
            )
        )
    db.commit()

    for bad in ("best pizza near me", "car insurance quote", "dental insurance plan"):
        _shown(db, client_a, bad, 350, position=22)
    _shown(db, client_a, "heat pump rebate orlando", 350, position=22)
    candidates, summary, _ = demand_candidates(db, client_a, today=TODAY)
    assert [g.term for g in candidates] == ["heat pump rebate orlando"]
    assert summary["demand_off_topic"] == 3


def test_emd_rival_domain_keeps_geo_industry_queries_while_filtering_brand_intent(db, client_a):
    client_a.client_name = "Boys Electrical"
    client_a.domain = "boys-electrical.com"
    client_a.competitor_domains = ["orlando-electrical.com"]
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
        _page(db, client_a.id, slug, title)
    db.commit()

    _shown(db, client_a, "orlando electrical contractor", 420, position=20)
    _shown(db, client_a, "orlando electrical panel upgrade", 390, position=22)
    _shown(db, client_a, "orlando electrical reviews", 340, position=18)
    _shown(db, client_a, "orlando-electrical pricing", 310, position=18)

    candidates, summary, _ = demand_candidates(db, client_a, today=TODAY)
    assert {g.term for g in candidates} == {
        "orlando electrical contractor",
        "orlando electrical panel upgrade",
    }
    assert summary["demand_brand"] == 2


def test_vocab_sets_isolates_question_openers_and_gsc_tabs_newlines_trimmed(db, client_a):
    from app.services.demand_gaps import _vocab_sets

    _hvac_site(db, client_a)
    url_how = "https://example.com/how-to-pick-hvac"
    url_it = "https://example.com/it-consulting"
    for url, title in ((url_how, "How to Pick an HVAC System"), (url_it, "IT Consulting")):
        db.add(
            FactCrawlPageSnapshot(
                id=uuid4(),
                client_id=client_a.id,
                source=CRAWL_SOURCE_FIRST_PARTY,
                snapshot_date=DAY,
                raw_url=url,
                normalized_url=url,
                status_code=200,
                indexable=True,
                word_count=600,
                inbound_internal_links=4,
                inbound_editorial_links=2,
                redirect_count=0,
                title=title,
                sections=[{"heading": title}],
            )
        )
    db.commit()
    pages = {
        row.normalized_url: row
        for row in db.query(FactCrawlPageSnapshot).filter(
            FactCrawlPageSnapshot.client_id == client_a.id
        )
    }
    core_vocab, _ = _vocab_sets(db, client_a, pages)
    assert "it" in core_vocab

    _shown(db, client_a, "\t\ngeothermal   heat pump   repair\n\t", 50, position=22)
    _rival_rank(
        db,
        client_a,
        "rivalhvac.com",
        "geothermal heat pump repair",
        position=3,
        volume=650,
        difficulty=24,
    )
    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert [g.term for g in scan.gaps] == ["geothermal heat pump repair"]
    assert scan.gaps[0].impressions == 50.0


def test_hyphenated_brand_industry_rival_filtered_in_demand_candidates(db, client_a, client_b):
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
        _page(db, client_a.id, slug, title)
    db.commit()

    _shown(db, client_a, "jones electrical", 400, position=20)
    _shown(db, client_a, "jones electrical contractor", 380, position=21)
    _shown(db, client_a, "acme electric", 360, position=21)
    _shown(db, client_a, "orlando electrical reviews", 340, position=18)
    _shown(db, client_a, "orlando-electrical pricing", 310, position=18)
    _shown(db, client_a, "orlando electrical contractor", 420, position=20)
    _shown(db, client_a, "orlando electrical panel upgrade", 390, position=22)
    _shown(db, client_a, "palm bay electrical", 370, position=22)

    candidates, summary, _ = demand_candidates(db, client_a, today=TODAY)
    assert {g.term for g in candidates} == {
        "orlando electrical contractor",
        "orlando electrical panel upgrade",
        "palm bay electrical",
    }
    assert summary["demand_brand"] == 5

    _hvac_site(db, client_b)
    client_b.client_name = "Smith HVAC"
    client_b.domain = "smith-hvac.com"
    client_b.competitor_domains = ["jones-hvac.com"]
    db.commit()

    _shown(db, client_b, "jones hvac", 400, position=20)
    _shown(db, client_b, "jones hvac contractor", 350, position=21)
    _shown(db, client_b, "hvac maintenance checklist", 450, position=20)

    candidates_b, summary_b, _ = demand_candidates(db, client_b, today=TODAY)
    assert [g.term for g in candidates_b] == ["hvac maintenance checklist"]
    assert summary_b["demand_brand"] == 2


def test_promoted_priced_variant_updates_gsc_metrics_coverage_why_and_action(db, client_a):
    from app.services import content_gaps_view

    _hvac_site(db, client_a)
    _page(db, client_a.id, "rebates", "HVAC Rebates")
    db.commit()

    _shown(
        db,
        client_a,
        "air heat pump rebates",
        500,
        clicks=1,
        position=35,
        url="https://example.com/heat-pumps",
    )
    _shown(
        db,
        client_a,
        "air heat pump rebates orlando",
        250,
        clicks=20,
        position=14,
        url="https://example.com/rebates",
    )
    _price(db, client_a, "air heat pump rebates orlando", volume=800, difficulty=20)

    scan = scan_demand_gaps(db, client_a, today=TODAY)
    assert [g.term for g in scan.gaps] == ["air heat pump rebates orlando"]
    g = scan.gaps[0]
    assert g.impressions == 250.0
    assert g.clicks == 20.0
    assert g.position == 14.0
    assert g.stand_in_url == "https://example.com/rebates"
    assert g.absent_words == ("orlando",)
    assert g.best_overlap == 0.4
    assert g.nearest[0].url == "https://example.com/heat-pumps"
    assert g.nearest[0].shared == ("heat", "pump")
    assert g.also_covers == (("air heat pump rebates", 500.0),)

    view = content_gaps_view.build(db, client_a)
    assert len(view["gaps"]) == 1
    row = view["gaps"][0]
    assert row["term"] == "air heat pump rebates orlando"
    assert row["impressions"] == 250
    assert row["clicks"] == 20
    assert row["position"] == 14.0
    assert row["page_now"] == "https://example.com/rebates"
    assert row["why"] == "No page on the site uses orlando."
    assert row["action"] == "Write a new page"
    assert row["also_covers"] == ["air heat pump rebates"]


def test_tracked_or_excluded_rival_keyword_does_not_leak_into_rival_core_vocab(db, client_a):
    from app.models.watch_target import WatchTarget
    from app.services.demand_gaps import competitor_candidates

    _hvac_site(db, client_a)
    client_a.client_name = "Smith HVAC"
    client_a.domain = "smith-hvac.com"
    client_a.competitor_domains = ["jones-hvac.com"]
    client_a.primary_market = "Orlando, FL"
    db.add(
        FactSerKeyword(
            id=uuid4(),
            client_id=client_a.id,
            site_engine_id="1",
            keyword_id="kw-jones",
            keyword="jones hvac",
            is_tracked=True,
            volume=500,
        )
    )
    db.add(
        WatchTarget(
            id=uuid4(),
            client_id=client_a.id,
            kind="keyword",
            item_key="k-jones",
            text="jones hvac",
            state="excluded",
        )
    )
    db.commit()

    _shown(db, client_a, "jones hvac contractor", 400, position=20)
    _rival_rank(
        db,
        client_a,
        "jones-hvac.com",
        "jones hvac installation",
        position=2,
        volume=600,
        difficulty=22,
    )

    candidates, summary, _ = demand_candidates(db, client_a, today=TODAY)
    assert candidates == []
    assert summary["demand_brand"] == 1

    comp_gaps, comp_summary = competitor_candidates(db, client_a, skip=set(), today=TODAY)
    assert comp_gaps == []
    assert comp_summary["competitor_brand"] == 1


def test_raw_demand_candidates_merges_whitespace_variants_per_url_before_earning_check(
    db, client_a
):
    _hvac_site(db, client_a)
    repair_url = "https://example.com/ac-repair"
    duct_url = _page(db, client_a.id, "duct-work", "Duct Work Services")
    db.commit()

    # Same URL split by \t / \n (PostgreSQL trim()/btrim() leaves internal tabs/newlines uncollapsed)
    _shown(db, client_a, "heat\tpump\nrebates", 60, position=5, url=repair_url)
    _shown(db, client_a, "heat pump rebates", 60, position=20, url=repair_url)

    # Split across two URLs where merging /ac-repair rows (80@22) beats /duct-work (50@6)
    _shown(db, client_a, "mini\tsplit\nac\ninstallation", 40, position=22, url=repair_url)
    _shown(db, client_a, "mini split ac installation", 40, position=22, url=repair_url)
    _shown(db, client_a, "mini split ac installation", 50, position=6, url=duct_url)

    candidates, summary, _ = demand_candidates(db, client_a, today=TODAY)
    by_term = {g.term: g for g in candidates}
    assert set(by_term) == {"heat pump rebates", "mini split ac installation"}
    assert summary["demand_earning"] == 0

    hp = by_term["heat pump rebates"]
    assert hp.impressions == 120.0
    assert hp.position == 12.5
    assert hp.stand_in_url == repair_url

    mini = by_term["mini split ac installation"]
    assert mini.stand_in_url == repair_url
    assert mini.impressions == 130.0
    assert abs(mini.position - (80 * 22 + 50 * 6) / 130) < 1e-6


def test_tampa_bay_primary_market_does_not_leak_bay_into_rival_core_vocab(db, client_a):
    from app.services import content_gaps_view
    from app.services.demand_gaps import competitor_candidates

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
        _page(db, client_a.id, slug, title)
    _page(db, client_a.id, "about-us", "About Us")
    db.commit()

    _shown(db, client_a, "bay hvac", 400, position=20)
    _shown(db, client_a, "tampa bay hvac contractor", 450, position=22)
    _price(db, client_a, "tampa bay hvac contractor", volume=500, difficulty=20)
    _rival_rank(
        db,
        client_a,
        "bay-hvac.com",
        "bay hvac",
        position=2,
        volume=600,
        difficulty=22,
    )
    _rival_rank(
        db,
        client_a,
        "tampa-bay-hvac.com",
        "tampa bay hvac contractor",
        position=3,
        volume=500,
        difficulty=20,
    )

    candidates, summary, _ = demand_candidates(db, client_a, today=TODAY)
    assert [g.term for g in candidates] == ["tampa bay hvac contractor"]
    assert summary["demand_brand"] == 1

    comp_gaps, comp_summary = competitor_candidates(db, client_a, skip=set(), today=TODAY)
    assert [g.term for g in comp_gaps] == ["tampa bay hvac contractor"]
    assert comp_summary["competitor_brand"] == 1

    view = content_gaps_view.build(db, client_a)
    assert [g["term"] for g in view["gaps"]] == ["tampa bay hvac contractor"]


def test_ft_lauderdale_primary_market_and_plural_possessive_rivals(db, client_a):
    from app.services import content_gaps_view
    from app.services.demand_gaps import competitor_candidates

    client_a.client_name = "Suncoast Electrical"
    client_a.domain = "suncoast-electrical.com"
    client_a.primary_market = "Ft. Lauderdale, FL"
    client_a.competitor_domains = [
        "lauderdale-electrical.com",
        "ft-lauderdale-electrical.com",
        "jones-plumbing.com",
    ]
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
        _page(db, client_a.id, slug, title)
    _page(db, client_a.id, "about-us", "About Us")
    db.commit()

    _shown(db, client_a, "lauderdale electrical", 400, position=20)
    _shown(db, client_a, "jones’ plumbing", 350, position=20)
    _shown(db, client_a, "ft. lauderdale electrical contractor", 450, position=22)
    _price(db, client_a, "ft. lauderdale electrical contractor", volume=500, difficulty=20)
    _rival_rank(
        db,
        client_a,
        "lauderdale-electrical.com",
        "lauderdale electrical",
        position=2,
        volume=600,
        difficulty=22,
    )
    _rival_rank(
        db,
        client_a,
        "jones-plumbing.com",
        "jones' plumbing",
        position=1,
        volume=500,
        difficulty=20,
    )
    _rival_rank(
        db,
        client_a,
        "ft-lauderdale-electrical.com",
        "ft. lauderdale electrical contractor",
        position=3,
        volume=500,
        difficulty=20,
    )

    candidates, summary, _ = demand_candidates(db, client_a, today=TODAY)
    assert [g.term for g in candidates] == ["ft. lauderdale electrical contractor"]
    assert summary["demand_brand"] == 2

    comp_gaps, comp_summary = competitor_candidates(db, client_a, skip=set(), today=TODAY)
    assert [g.term for g in comp_gaps] == ["ft. lauderdale electrical contractor"]
    assert comp_summary["competitor_brand"] == 2

    view = content_gaps_view.build(db, client_a)
    assert [g["term"] for g in view["gaps"]] == ["ft. lauderdale electrical contractor"]
