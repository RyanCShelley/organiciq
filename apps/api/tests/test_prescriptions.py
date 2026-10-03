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


def test_no_page_at_all_asks_for_the_mapping_before_building():
    p = _kw(page_url=None, page_impressions=0.0, page_position=None)
    assert p.cause == "no_page_for_term"
    assert p.steps[0].human is True
    assert "Name the page that should own" in p.steps[0].text
    assert "write one that targets" in p.steps[1].text


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
    assert "Name the page that should own" in p.steps[0].text


def test_the_expected_result_is_not_phrased_as_a_ranking_failure():
    """"3 impressions at position 1 that are not converting to rank" says a
    page ranking first is failing to rank."""
    p = _kw()
    assert "not converting to rank" not in (p.expected_impact or "")
    assert "monthly searches" in (p.expected_impact or "")


def test_the_page_is_never_guessed_from_a_title():
    """Matching "seo services" against titles chose /capabilities/local-seo,
    which is a different term with a different page. A wrong page is worse
    than no page, because someone acts on it."""
    p = _kw(page_url="https://smamarketing.com/", page_impressions=3.0)
    assert p.cause == "no_page_for_term"
    assert p.steps[0].human is True
    assert "guessing from page titles" in p.steps[0].detail


def test_the_card_never_claims_nothing_exists_beside_an_impression_count():
    """It read "nothing draws a single impression" with "page impressions 3"
    printed directly above it."""
    p = _kw(page_url="https://smamarketing.com/", page_impressions=3.0)
    assert p.cause == "no_page_for_term"
    detail = p.steps[0].detail
    assert "3 impressions" in detail
    assert "too few to call it the page" in detail


# ── Lever 3: where a site-wide drop actually sits ──


def _site(**kwargs):
    from app.decisions.site_conversion_cause import (
        SiteConversionSignals,
        classify_site_conversion,
    )

    base = dict(leads_now=10.0, leads_before=30.0)
    base.update(kwargs)
    return classify_site_conversion(SiteConversionSignals(**base))


def test_a_drop_sitting_in_one_page_group_is_handed_to_that_page():
    p = _site(loss_by_group=[("https://x/services", 15.0), ("https://x/blog", 5.0)])
    assert p.cause == "drop_concentrated"
    assert p.routed_to == "converting_page_dropped"
    assert "rather than the site" in p.steps[0].text


def test_a_drop_spread_evenly_looks_for_what_changed_globally():
    p = _site(loss_by_group=[("https://x/a", 7.0), ("https://x/b", 7.0), ("https://x/c", 6.0)])
    assert p.cause == "drop_sitewide"
    assert "consent banner" in p.steps[0].detail


def test_the_same_fall_as_last_year_is_the_calendar():
    """Every other cause is a reason to change something. This one is a
    reason not to, so it is checked first."""
    p = _site(leads_year_ago=10.0, leads_year_before_that=30.0)
    assert p.cause == "seasonal"
    assert "hold the plan" in p.steps[0].text


def test_a_site_short_of_plan_that_did_not_fall_is_sent_somewhere_specific():
    """Telling someone to find what changed, when nothing did, sends them
    looking for nothing."""
    p = _site(
        leads_now=20.0,
        leads_before=20.0,
        period_goal=50.0,
        weakest_pages=[("https://x/pricing", 900.0, 0.2)],
    )
    assert p.cause == "behind_plan"
    assert p.steps[0].target == "https://x/pricing"
    assert "900 sessions a period converting at 0.20%" in p.steps[0].detail


def test_the_segments_we_cannot_read_are_named_not_skipped():
    p = _site(loss_by_group=[("https://x/a", 7.0), ("https://x/b", 7.0), ("https://x/c", 6.0)])
    byhand = [s for s in p.steps if s.human]
    assert any("device or visitor type" in (s.detail or "") for s in byhand)


# ── Lever 4: the listing, with a title drafted ──


def _ctr(**kwargs):
    from app.decisions.ctr_cause import CtrSignals, classify_ctr_gap

    base = dict(
        page_url="https://aquamanleakdetection.com/",
        top_query="pool leak detection",
        impressions=5000.0,
        clicks=40.0,
        ctr_percent=0.8,
        expected_ctr_percent=3.89,
        recoverable_clicks=150.0,
        title="Aquaman Leak Detection | Trusted Since 2004",
        description="We find leaks.",
        brand="Aquaman",
    )
    base.update(kwargs)
    return classify_ctr_gap(CtrSignals(**base))


def test_the_card_drafts_the_replacement_title():
    """"Rewrite the title" is not an instruction until it says to what."""
    p = _ctr()
    assert "Try: “Pool leak detection" in p.steps[0].detail
    assert "does not contain the query" in p.steps[0].detail


def test_the_drafted_title_does_not_repeat_the_brand():
    from app.decisions.ctr_cause import draft_title

    assert draft_title(
        "pool leak detection", "Aquaman", "Aquaman Leak Detection | Trusted Since 2004"
    ) == "Pool leak detection — Trusted Since 2004 | Aquaman"


def test_a_title_that_already_leads_with_the_query_is_told_what_else_to_add():
    p = _ctr(title="Pool leak detection | Aquaman")
    assert "reads like every other result" in p.steps[0].detail


def test_an_ai_overview_gets_its_own_step():
    """A better title cannot win back a click the answer already satisfied."""
    p = _ctr(ai_overview=True)
    assert any("AI Overview" in step.text for step in p.steps)


def test_the_serp_comparison_we_cannot_make_is_named():
    human = [s for s in _ctr().steps if s.human]
    assert len(human) == 1
    assert "rendered titles are not stored" in human[0].detail


# ── Lever 6: donor, anchor, target ──


def _link(**kwargs):
    from app.decisions.link_cause import Donor, LinkSignals, classify_link_gap

    base = dict(
        page_url="https://x/target",
        position=9.0,
        inbound_links=2,
        floor=6,
        donors=[Donor("https://x/guide", "pool leak detection", 420.0, 5)],
        recoverable_clicks=60.0,
    )
    base.update(kwargs)
    return classify_link_gap(LinkSignals(**base))


def test_the_donor_the_anchor_and_the_target_are_all_named():
    p = _link()
    assert p.steps[0].target == "https://x/guide"
    assert "“pool leak detection” as the anchor" in p.steps[0].detail
    assert "not the navigation" in p.steps[0].detail


def test_with_no_donor_it_says_so_rather_than_repeating_itself():
    """"Add internal links from mapped authoritative pages" named no page."""
    p = _link(donors=[])
    assert p.steps[0].human is True
    assert "no page on the site both shares a search query" in p.steps[0].detail


def test_placing_the_link_is_the_part_we_cannot_do():
    human = [s for s in _link().steps if s.human]
    assert any("body text is not stored" in (s.detail or "") for s in human)


def test_internal_linking_names_which_situation_it_is_in():
    """It knows whether a donor exists; reporting "undetermined" for both
    threw that away."""
    assert _link().cause == "under_linked_donors_found"
    assert _link(donors=[]).cause == "under_linked_no_donor"


# ── The keyword-to-page map, and the band below the top five ──


def test_the_map_beats_search_console():
    """Search Console on a term the client does not rank for reports either
    nothing or the wrong page. A person saying it once settles it."""
    p = _kw(
        page_url="https://smamarketing.com/",
        page_impressions=3.0,
        mapped_url="https://smamarketing.com/capabilities/seo",
    )
    assert p.cause == "page_not_competitive"
    assert p.evidence["matched_page"] == "https://smamarketing.com/capabilities/seo"


def test_a_recorded_no_page_is_an_answer_not_a_question():
    """Asking again is the engine forgetting what it was told."""
    p = _kw(page_url=None, page_impressions=0.0, page_position=None, mapping_recorded=True)
    assert p.cause == "no_page_for_term"
    assert "Write the page that targets" in p.steps[0].text
    assert not any(s.text.startswith("Name the page") for s in p.steps)


def _push(**kwargs):
    from app.decisions.rank_push_cause import (
        RankPushDonor,
        RankPushSignals,
        classify_rank_push,
    )

    base = dict(
        page_url="https://x/guide",
        top_query="pool leak repair",
        position=7.4,
        impressions=4200.0,
        clicks=28.0,
        clicks_at_target=45.0,
        inbound_links=2,
        link_floor=6,
        donors=[RankPushDonor("https://x/blog", "pool leak repair", 380.0)],
        word_count=900,
    )
    base.update(kwargs)
    return classify_rank_push(RankPushSignals(**base))


def test_below_the_top_five_the_instruction_is_rank_not_the_listing():
    """The curve pays 0.73% at position six. There is no click to win back
    by rewriting a listing, so a better title is not the work."""
    p = _push()
    assert p.cause == "rank_push"
    actions = " ".join(s.text for s in p.steps)
    assert "title" not in actions.lower()
    assert "Link to this page" in actions


def test_it_quantifies_the_band_in_clicks():
    assert _push().expected_impact == "about 17 clicks a period at position five"


def test_with_no_donor_it_asks_the_hub_for_the_link():
    p = _push(donors=[])
    assert "from the section it belongs to" in p.steps[0].text


def test_the_content_comparison_is_the_human_step():
    human = [s for s in _push().steps if s.human]
    assert len(human) == 1
    assert "top five results" in human[0].text
    assert "900 words" in human[0].detail
