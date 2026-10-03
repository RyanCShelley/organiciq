"""Three things the crawler could always see and was throwing away.

Each was written off as "no data source" because SE Ranking's audit has no
check for it. SE Ranking is not the only crawler here — the first-party one
fetches the DOM and already loads robots.txt, which is everything these
need.
"""

from __future__ import annotations

from urllib import robotparser

from app.ingestion.crawler.fetch import _blocked_resource_count
from app.ingestion.crawler.parse import parse_page
from app.services.lever_engine import (
    GrowthAction,
    detect_technical_signal,
    is_core_work_signal,
    signal_lever,
)
from tests.test_phase3_technical import _crawl

LIMITS = {"cta_min_sessions": 30, "orphan_min_impressions": 30}


def _robots(body: str, url: str = "https://example.com/robots.txt"):
    parser = robotparser.RobotFileParser()
    parser.set_url(url)
    parser.parse(body.splitlines())
    return parser


# ── Soft 404s ──


def test_a_page_that_says_404_while_returning_200_is_detected():
    parsed = parse_page(
        url="https://example.com/gone",
        body="<html><head><title>404: Page Not Found</title></head><body></body></html>",
    )
    assert parsed.says_not_found is True


def test_prose_about_something_not_being_found_is_not_a_soft_404():
    """"Not found" in a sentence is ordinary writing."""
    parsed = parse_page(
        url="https://example.com/guide",
        body=(
            "<html><head><title>What to do when your keys are not found</title>"
            "</head><body><h1>Lost keys guide</h1></body></html>"
        ),
    )
    assert parsed.says_not_found is False


def test_a_soft_404_is_blocking_and_prescribes_the_fix():
    detected = detect_technical_signal(
        "https://example.com/gone", _crawl(soft_404=True), thresholds=LIMITS
    )
    assert detected is not None
    assert detected.audit_signal == "soft_404"
    assert not is_core_work_signal("soft_404")


def test_a_real_404_outranks_the_soft_one():
    detected = detect_technical_signal(
        "https://example.com/gone",
        _crawl(soft_404=True, status_code=404),
        thresholds=LIMITS,
    )
    assert detected is not None
    assert detected.audit_signal == "status_error"


# ── Render-critical resources ──


def test_scripts_and_stylesheets_are_extracted():
    parsed = parse_page(
        url="https://example.com/p",
        body=(
            "<html><head><link rel='stylesheet' href='/theme.css'>"
            "<script src='/bundle.js'></script></head><body></body></html>"
        ),
    )
    assert parsed.resource_urls == [
        "https://example.com/bundle.js",
        "https://example.com/theme.css",
    ]


def test_a_disallowed_stylesheet_is_counted():
    parsed = parse_page(
        url="https://example.com/p",
        body="<html><head><link rel='stylesheet' href='/assets/theme.css'></head></html>",
    )
    robots = _robots("User-agent: *\nDisallow: /assets/")
    assert _blocked_resource_count(parsed, robots) == 1


def test_an_allowed_resource_is_not():
    parsed = parse_page(
        url="https://example.com/p",
        body="<html><head><link rel='stylesheet' href='/theme.css'></head></html>",
    )
    assert _blocked_resource_count(parsed, _robots("User-agent: *\nDisallow: /admin/")) == 0


def test_a_cdn_is_left_alone():
    """Another host has its own robots.txt and we have not read it.

    Guessing would turn every site using a CDN into a finding.
    """
    parsed = parse_page(
        url="https://example.com/p",
        body="<html><head><script src='https://cdn.other.com/assets/app.js'></script></head></html>",
    )
    robots = _robots("User-agent: *\nDisallow: /assets/")
    assert _blocked_resource_count(parsed, robots) == 0


def test_blocked_resources_are_blocking_and_say_how_many():
    detected = detect_technical_signal(
        "https://example.com/p", _crawl(blocked_resources=2), thresholds=LIMITS
    )
    assert detected is not None
    assert detected.audit_signal == "blocked_resources"
    assert "2 scripts or stylesheets" in detected.diagnosis
    assert not is_core_work_signal("blocked_resources")


# ── Nothing to convert through ──


def test_forms_phone_links_and_cta_buttons_all_count():
    parsed = parse_page(
        url="https://example.com/p",
        body=(
            "<html><body><form></form><a href='tel:5550101'>Ring us</a>"
            "<button>Get a quote</button></body></html>"
        ),
    )
    assert parsed.conversion_elements == 3


def test_a_page_with_nothing_to_convert_through_counts_zero():
    parsed = parse_page(
        url="https://example.com/p",
        body="<html><body><p>Some words about a topic.</p></body></html>",
    )
    assert parsed.conversion_elements == 0


def test_a_page_with_traffic_and_no_cta_is_conversion_work():
    detected = detect_technical_signal(
        "https://example.com/p",
        _crawl(conversion_elements=0),
        sessions=120.0,
        thresholds=LIMITS,
    )
    assert detected is not None
    assert detected.audit_signal == "no_conversion_element"
    assert signal_lever("no_conversion_element") == GrowthAction.CONVERSION_PATH.value


def test_a_page_nobody_visits_is_not_worth_saying_this_about():
    assert (
        detect_technical_signal(
            "https://example.com/p",
            _crawl(conversion_elements=0),
            sessions=4.0,
            thresholds=LIMITS,
        )
        is None
    )


def test_a_crawl_that_predates_the_check_is_not_a_finding():
    """Null means nobody looked. Reading it as zero would report every page
    crawled before this shipped as having no way to convert."""
    assert (
        detect_technical_signal(
            "https://example.com/p",
            _crawl(conversion_elements=None),
            sessions=500.0,
            thresholds=LIMITS,
        )
        is None
    )
