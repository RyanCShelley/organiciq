"""Every finding says what to do, and names the cause it decided on.

The reports answer the gates — leads down, page slipped. The engine exists
to say what to do about it, and a card reading "review traffic and UX" has
handed that back to the reader.
"""

from __future__ import annotations

import pytest

from app.decisions.page_drop_cause import PageDropSignals, classify_page_drop
from app.decisions.prescription import CAUSES, Prescription, Step
from app.decisions.tracking_cause import TrackingSignals, classify_tracking_break


# ── The contract ──


def test_a_step_that_says_review_is_rejected():
    for text in ("Review the page", "Look at the form", "Investigate the drop"):
        with pytest.raises(ValueError, match="not an action"):
            Prescription(cause="undetermined", steps=[Step(text)])


def test_a_prescription_with_no_steps_is_rejected():
    with pytest.raises(ValueError, match="no steps"):
        Prescription(cause="undetermined", steps=[])


def test_an_unknown_cause_is_rejected():
    with pytest.raises(ValueError, match="unknown cause"):
        Prescription(cause="vibes", steps=[Step("Do the thing")])


def test_every_cause_has_a_sentence_explaining_it():
    assert all(text and text[0].isupper() for text in CAUSES.values())


# ── Lever 1: which part of tracking broke ──


def _tracking(**kwargs):
    base = dict(
        sessions_now=500.0,
        sessions_before=500.0,
        search_clicks_now=400.0,
        search_clicks_before=420.0,
        leads_now=0.0,
        crm_leads_now=None,
    )
    base.update(kwargs)
    return classify_tracking_break(TrackingSignals(**base))


def test_sessions_gone_while_google_still_reports_clicks_is_the_tag():
    """Search clicks are the witness that does not depend on our own tag."""
    p = _tracking(sessions_now=20.0)
    assert p.cause == "analytics_tag_broken"
    assert "Re-add the GA4 tag" in p.steps[0].text


def test_sessions_and_clicks_both_gone_is_not_the_tag():
    """The site really did lose its traffic. Re-adding the tag fixes nothing."""
    assert _tracking(sessions_now=20.0, search_clicks_now=10.0).cause != "analytics_tag_broken"


def test_the_crm_still_receiving_means_the_event_not_the_form():
    p = _tracking(crm_leads_now=12.0)
    assert p.cause == "conversion_event_broken"
    assert any("Republish the tag manager" in step.text for step in p.steps)


def test_neither_the_crm_nor_ga4_means_the_form():
    p = _tracking(crm_leads_now=0.0)
    assert p.cause == "form_broken"
    assert any("spam filter" in step.text for step in p.steps)


def test_one_quiet_page_while_the_rest_convert_is_a_partial_break():
    p = _tracking(leads_now=8.0, silent_pages=("https://x/quote",))
    assert p.cause == "partial_tracking_break"
    assert p.steps[0].target == "https://x/quote"


def test_with_no_crm_it_asks_for_the_one_test_that_separates_them():
    """Guessing between the form and the event wastes the afternoon either way."""
    p = _tracking()
    assert p.evidence["crm_connected"] is False
    assert "DebugView and the inbox together" in p.steps[0].text
    assert "No CRM is connected" in p.steps[0].detail


# ── Lever 2: which side of leads = sessions x rate moved ──


def _drop(**kwargs):
    base = dict(
        page_url="https://x/services",
        sessions_now=500.0,
        sessions_before=500.0,
        rate_now=0.5,
        rate_before=3.0,
        leads_lost=12.0,
        conversion_elements=3,
    )
    base.update(kwargs)
    return classify_page_drop(PageDropSignals(**base))


def test_traffic_gone_is_routed_rather_than_prescribed():
    """Rewriting a page cannot buy back traffic it is not getting."""
    p = _drop(sessions_now=100.0, rate_now=3.0)
    assert p.cause == "sessions_fell"
    assert p.routed_to == "decaying_page"
    assert "not a page problem" in p.steps[0].text


def test_a_page_that_lost_its_form_says_exactly_that():
    p = _drop(conversion_elements=0)
    assert p.cause == "page_changed"
    assert "Put the form or call to action back" in p.steps[0].text


def test_a_steady_page_and_a_steady_rate_is_not_a_finding():
    assert _drop(rate_now=2.9, leads_lost=0.0) is None


def test_no_cause_found_still_names_an_experiment():
    """"Undetermined" is not permission to say "review it"."""
    p = _drop()
    assert p.cause == "undetermined"
    assert "A/B test" in p.steps[0].text
    assert p.verify_metric == "page_lead_rate"


def test_every_prescription_can_be_verified():
    for p in (_tracking(), _tracking(sessions_now=20.0), _drop(), _drop(conversion_elements=0)):
        assert p.verify_metric
        assert p.verify_after_days > 0
        assert p.expected_impact


def test_traffic_tripling_is_the_mix_changing_not_the_page_breaking():
    """Element 6's homepage: 4,702 sessions to 13,191, rate 0.66% to 0.14%.
    The engine said "no cause found" because it only looked for a fall."""
    p = _drop(sessions_before=4702.0, sessions_now=13191.0, rate_before=0.66, rate_now=0.14)
    assert p.cause == "traffic_mix_shifted"
    assert "Leave the page's main offer alone" in p.steps[0].text
    assert p.evidence["sessions_change_pct"] == 180.5


# ── Lever 7: which of five things is missing ──


def _kw(**kwargs):
    from app.decisions.keyword_cause import KeywordSignals, classify_keyword_gap

    base = dict(
        keyword="seo services",
        volume=74000.0,
        difficulty=72.0,
        page_url="https://smamarketing.com/capabilities/seo",
        page_impressions=1240.0,
        page_position=38.0,
        indexable=True,
        canonical_elsewhere=False,
        in_sitemap=True,
        inbound_internal_links=9,
        title="SEO Agency That Understands AI Search",
    )
    base.update(kwargs)
    return classify_keyword_gap(KeywordSignals(**base))


def test_no_page_at_all_is_the_only_case_that_says_build_one():
    p = _kw(page_url=None, page_impressions=0.0, page_position=None)
    assert p.cause == "no_page_for_term"
    assert "Write a page that targets" in p.steps[0].text


def test_a_page_that_cannot_be_indexed_is_fixed_before_its_content():
    """No amount of content work moves a page Google cannot index."""
    p = _kw(indexable=False)
    assert p.cause == "page_cannot_rank"
    assert "not indexable" in p.steps[0].text
    assert "No amount of content work" in p.steps[0].detail


def test_a_page_nothing_links_to_is_also_blocked():
    p = _kw(inbound_internal_links=1)
    assert p.cause == "page_cannot_rank"
    assert "1 internal links point at it" in p.steps[0].text


def test_a_title_missing_the_term_is_named_with_the_current_title():
    p = _kw()
    assert p.cause == "page_not_competitive"
    assert "Put “seo services” in the title" in p.steps[0].text
    assert "SEO Agency That Understands AI Search" in p.steps[0].detail


def test_a_hard_term_gets_a_long_tail_step():
    assert any("long-tail" in step.text for step in _kw(difficulty=85).steps)
    assert not any("long-tail" in step.text for step in _kw(difficulty=20).steps)


def test_the_serp_step_is_marked_human_because_we_do_not_store_it():
    serp = [s for s in _kw().steps if "top three results" in s.text]
    assert len(serp) == 1
    assert serp[0].human is True


# ── Lever 8: why an engine does not cite us ──


def _prompt(**kwargs):
    from app.decisions.prompt_cause import PromptSignals, classify_prompt_gap

    base = dict(prompt="who are the best SEO agencies in Florida", checks=3)
    base.update(kwargs)
    return classify_prompt_gap(PromptSignals(**base))


def test_a_blocked_ai_crawler_comes_before_everything_else():
    """An engine that cannot fetch the page will never cite it."""
    p = _prompt(blocked_crawlers=("GPTBot", "ClaudeBot"), best_page="https://x/p")
    assert p.cause == "ai_crawlers_blocked"
    assert "Allow GPTBot, ClaudeBot in robots.txt" in p.steps[0].text


def test_no_matching_page_asks_for_one_with_the_question_as_its_heading():
    p = _prompt()
    assert p.cause == "no_page_answers_prompt"
    assert "40 to 60 word" in p.steps[0].detail


def test_a_page_that_exists_is_made_quotable_rather_than_replaced():
    p = _prompt(best_page="https://x/agencies")
    assert p.cause == "page_not_quotable"
    assert all(
        step.target == "https://x/agencies" for step in p.steps if step.target
    )


def test_the_missing_citation_layer_becomes_a_named_human_check():
    """Who is cited instead lives in SE Visible and is not ingested. The
    spec says name the check rather than go quiet."""
    p = _prompt(best_page="https://x/agencies", citations_known=False)
    human = [step for step in p.steps if step.human]
    assert len(human) == 1
    assert "not ingested" in human[0].detail


def test_a_handful_of_impressions_does_not_make_it_the_page_for_the_term():
    """The homepage picked up three impressions for "seo services" and the
    engine told someone to rewrite its title. Three impressions is noise."""
    p = _kw(page_url="https://smamarketing.com/", page_impressions=3.0, page_position=1.0)
    assert p.cause == "no_page_for_term"
    assert "Write a page that targets" in p.steps[0].text


def test_the_expected_result_is_not_phrased_as_a_ranking_failure():
    """"3 impressions at position 1 that are not converting to rank" says a
    page ranking first is failing to rank."""
    p = _kw()
    assert "not converting to rank" not in (p.expected_impact or "")
    assert "monthly searches" in (p.expected_impact or "")


def test_a_page_title_finds_what_search_console_missed():
    """/capabilities/seo is plainly the SEO services page. Search Console
    reported the homepage on three impressions, so the engine declared the
    page did not exist and asked for it to be built a second time."""
    p = _kw(
        page_url="https://smamarketing.com/",
        page_impressions=3.0,
        title_match_url="https://smamarketing.com/capabilities/seo",
    )
    assert p.cause == "page_not_competitive"
    assert p.evidence["matched_page"] == "https://smamarketing.com/capabilities/seo"
    assert p.steps[0].target == "https://smamarketing.com/capabilities/seo"


def test_the_card_never_claims_nothing_exists_beside_an_impression_count():
    """It read "nothing draws a single impression" with "page impressions 3"
    printed directly above it."""
    p = _kw(page_url="https://smamarketing.com/", page_impressions=3.0, title_match_url=None)
    assert p.cause == "no_page_for_term"
    detail = p.steps[0].detail
    assert "3 impressions" in detail
    assert "too few to call it the page" in detail
