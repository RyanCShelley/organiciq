"""The action catalog: what to do about a scored target.

Every action names a page, says what done looks like, and carries the metric
it will be judged on. "Improve the content" is the sentence this module
exists to stop producing — a prescription nobody can tell you have finished
is a prescription nobody finishes.
"""

from __future__ import annotations

from app.decisions.catalog import (
    BLOCKED_ACTIONS,
    VISIBILITY_ACTIONS,
    PageFacts,
    prescribe,
    v1_term_in_high_value_spots,
    v2_answer_block,
    v3_entity_markup,
    v4_internal_links,
    v6_rehoming,
)
from app.decisions.targets import Candidate, score_candidate


def _target(**kw):
    base = dict(
        keyword="local seo agency", target_url="https://x/local-seo",
        ranking_url="https://x/local-seo", position=12.0, volume=1000.0,
        priority=True, target_page_type="commercial",
    )
    base.update(kw)
    return score_candidate(Candidate(**base))


def _page(**kw) -> PageFacts:
    base = dict(
        url="https://x/local-seo",
        title="Local SEO Agency | X",
        description="We are a local seo agency.",
        headings=("What a local seo agency does",),
        entity_properties=frozenset({"about"}),
        inbound_editorial_links=10,
        site_median_links=5.0,
    )
    base.update(kw)
    return PageFacts(**base)


def test_v1_fires_when_the_page_never_says_the_phrase():
    found = v1_term_in_high_value_spots(_target(), _page(title="Services | X", headings=()))
    assert found is not None
    assert found.action_id == "V-1"
    assert "the title" in found.why and "any heading" in found.why


def test_v1_is_phrase_aware_not_a_bag_of_words():
    """'agency seo local' is not 'local seo agency'. A bag of words reported
    a page that never says the phrase as already optimised for it."""
    scrambled = _page(
        title="Agency for SEO, local", description="seo local agency", headings=("agency",)
    )
    assert v1_term_in_high_value_spots(_target(), scrambled) is not None


def test_v1_is_silent_when_the_page_already_uses_the_term():
    assert v1_term_in_high_value_spots(_target(), _page()) is None


def test_v2_only_fires_on_a_question():
    assert v2_answer_block(_target(keyword="local seo agency"), _page()) is None
    found = v2_answer_block(_target(keyword="what is local seo"), _page(faq_questions=()))
    assert found is not None and found.action_id == "V-2"


def test_v2_is_silent_when_the_page_already_asks_it():
    target = _target(keyword="what is local seo")
    page = _page(faq_questions=("What is local SEO and who needs it?",))
    assert v2_answer_block(target, page) is None


def test_v3_fires_only_without_entity_markup():
    assert v3_entity_markup(_target(), _page()) is None
    found = v3_entity_markup(_target(), _page(entity_properties=frozenset()))
    assert found is not None and "about" in found.done_when


def test_v4_compares_to_this_sites_median_not_a_constant():
    """A five-page site links everything from everywhere for legitimate
    reasons."""
    assert v4_internal_links(_target(), _page(inbound_editorial_links=10, site_median_links=5)) is None
    found = v4_internal_links(_target(), _page(inbound_editorial_links=1, site_median_links=8))
    assert found is not None
    assert "navigation does not count" in found.why.lower()


def test_v4_is_silent_when_the_site_has_no_median():
    assert v4_internal_links(_target(), _page(site_median_links=0)) is None


def test_v6_fires_when_the_wrong_page_ranks():
    found = v6_rehoming(_target(ranking_url="https://x/blog/local-seo-tips"), _page())
    assert found is not None
    assert found.metric == "Decision only"
    assert "nobody chose" in found.why


def test_re_homing_comes_before_optimising_the_page():
    """Optimising either page before the owner is settled is work on a page
    nobody chose."""
    target = _target(ranking_url="https://x/blog/other")
    found = prescribe(target, _page(title="Services | X", headings=()))
    assert found is not None and found.action_id == "V-6"


def test_the_term_goes_on_the_page_before_links_point_at_it():
    target = _target()
    page = _page(title="Services | X", headings=(), inbound_editorial_links=1, site_median_links=8)
    found = prescribe(target, page)
    assert found is not None and found.action_id == "V-1"


def test_every_action_says_what_done_looks_like():
    """A prescription nobody can tell you have finished is one nobody
    finishes."""
    cases = [
        (_target(ranking_url="https://x/other"), _page()),
        (_target(), _page(title="Services | X", headings=())),
        (_target(keyword="what is local seo"), _page(faq_questions=())),
        (_target(), _page(entity_properties=frozenset())),
        (_target(), _page(inbound_editorial_links=0, site_median_links=9)),
    ]
    for target, page in cases:
        found = prescribe(target, page)
        assert found is not None
        assert found.done_when and len(found.done_when) > 20
        assert found.metric
        assert found.target_url
        assert found.effort_min <= 60, found.action_id


def test_nothing_fires_on_a_healthy_page():
    assert prescribe(_target(), _page()) is None


def test_the_actions_that_cannot_fire_say_why():
    """Rather than being an action that silently never appears."""
    blocked = {a.action_id: a.reason for a in BLOCKED_ACTIONS}
    assert set(blocked) == {"V-5", "T-2"}
    assert all("SERP feature" in reason for reason in blocked.values())


def test_the_order_is_the_argument():
    assert VISIBILITY_ACTIONS[0] is v6_rehoming
    assert VISIBILITY_ACTIONS.index(v1_term_in_high_value_spots) < VISIBILITY_ACTIONS.index(
        v4_internal_links
    )
