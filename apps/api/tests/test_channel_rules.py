"""Any search engine is organic search.

The rules named google and bing, so every other engine fell through to Other
— the bucket the decision engine ignores. 146 Yahoo sessions and 97 from
DuckDuckGo in one month, plus Google Business Profile traffic, which is the
client's own local SEO work counted as somebody else's.
"""

from __future__ import annotations

from app.ingestion.channels import classify_channel
from app.models.config import ChannelRule, OrganicChannel


def _rule(priority, channel, source=None, medium=None, host=None) -> ChannelRule:
    return ChannelRule(
        match_source=source, match_medium=medium, match_host_contains=host,
        channel=channel, priority=priority, active=True,
    )


RULES = [
    _rule(10, OrganicChannel.AI_REFERRAL, host="chatgpt"),
    _rule(20, OrganicChannel.ORGANIC_SEARCH, source="google", medium="organic"),
    _rule(21, OrganicChannel.ORGANIC_SEARCH, source="bing", medium="organic"),
    _rule(25, OrganicChannel.ORGANIC_SEARCH, medium="organic"),
    _rule(26, OrganicChannel.ORGANIC_SEARCH, source="gmb"),
    _rule(27, OrganicChannel.REFERRAL, medium="referral"),
    _rule(40, OrganicChannel.PAID_SEARCH, source="google", medium="cpc"),
]


def test_a_search_engine_nobody_named_is_still_organic():
    """The whole bug. Both of these are really in the warehouse."""
    assert classify_channel("yahoo", "organic", RULES) is OrganicChannel.ORGANIC_SEARCH
    assert classify_channel("duckduckgo", "organic", RULES) is OrganicChannel.ORGANIC_SEARCH
    assert classify_channel("ecosia", "organic", RULES) is OrganicChannel.ORGANIC_SEARCH


def test_google_business_profile_is_the_clients_own_work():
    assert classify_channel("gmb", "gmb", RULES) is OrganicChannel.ORGANIC_SEARCH


def test_a_referral_is_a_referral_not_other():
    """Whether referrals count toward a client's outcomes is a scope
    decision, and it cannot be made while they are invisible."""
    assert classify_channel("linkedin.com", "referral", RULES) is OrganicChannel.REFERRAL


def test_paid_search_is_not_swept_up():
    """medium=cpc is not medium=organic, and the named rule still wins."""
    assert classify_channel("google", "cpc", RULES) is OrganicChannel.PAID_SEARCH


def test_an_ai_host_still_wins_over_the_generic_rule():
    assert classify_channel("chatgpt.com", "referral", RULES) is OrganicChannel.AI_REFERRAL


def test_direct_is_never_auto_classified_as_organic():
    assert classify_channel("(direct)", "(none)", RULES) is OrganicChannel.DIRECT_UNATTRIBUTED


def test_what_ga4_could_not_attribute_stays_other():
    """2,992 sessions a month arrive as (not set). Calling them organic
    would be inventing attribution."""
    assert classify_channel("(not set)", "(not set)", RULES) is OrganicChannel.OTHER
    assert classify_channel("(data not available)", "(data not available)", RULES) is OrganicChannel.OTHER
