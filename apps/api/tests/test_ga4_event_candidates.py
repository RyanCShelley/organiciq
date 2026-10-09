"""Which GA4 events get offered as leads.

Twenty of twenty-four clients have no `conversion_definitions`, which blocks
the whole Lead branch for them. The events have been in the warehouse the
whole time; the screen asked for them one at a time, typed by hand.

These are the names really in the warehouse on 9 Oct 2026, so a change that
stops recognising them fails here rather than on a client.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from app.models.config import ConversionDefinition
from app.models.ga4 import FactGa4Event, OrganicChannel
from app.services.ga4_event_candidates import (
    AUTOMATIC_EVENTS,
    load_event_candidates,
    looks_like_a_lead,
    suggested_label,
)

#: Verbatim from clients with no definitions set.
REAL_LEAD_EVENTS = [
    "form_submission",
    "form_submit",
    "form_fill",
    "phone_call",
    "phone_calls",
    "Phone Call / Email Click",
    "generate_lead",
    "Lead",
    "Conversion",
    "contact_sales_form_submission",
    # Snake_case defeated the first version of this: `\bsubmi` never fired
    # on `grade_submit`, because an underscore is a word character.
    "grade_submit",
    # A thank-you event is what fires after something was sent.
    "Form Submit - Thank You",
    "GA | Thank You Event",
    "jf_thank_you_request_quote",
    "jf_thank_you_general_inquiry",
]

REAL_NON_LEAD_EVENTS = [
    "GA4 | Analytics",
    "bucket_test",
    "cta_click",
    "geo_modal_shown",
    "geo_modal_dismissed",
    "geo_modal_cta_click",
    "page_view",
    "session_start",
    "first_visit",
    "user_engagement",
    "scroll",
    "click",
    "click_internal",
    "click_outbound",
    "video_start",
    "video_progress",
    "view_search_results",
    "file_download",
]


def test_the_real_lead_events_are_recognised():
    for name in REAL_LEAD_EVENTS:
        assert looks_like_a_lead(name), name


def test_the_real_noise_events_are_not():
    for name in REAL_NON_LEAD_EVENTS:
        assert not looks_like_a_lead(name), name


def test_form_start_is_not_a_lead():
    """The trap. Somebody touching a field is not somebody sending it, and
    the name is one character from the one that counts. Popfoam reports
    both."""
    assert looks_like_a_lead("form_submit")
    assert not looks_like_a_lead("form_start")


def test_a_genuinely_ambiguous_name_is_shown_and_not_ticked():
    """A gated download is a lead and a free one is not, and the name says
    nothing either way. These reach the screen unticked rather than being
    guessed at in either direction."""
    for name in ("pdf_download", "report_unlock"):
        assert not looks_like_a_lead(name), name


def test_an_event_somebody_named_conversion_is_taken_at_its_word():
    """GA4 never names an event `Conversion` by itself, so a client that has
    one meant it. Nashville Home Organizers does."""
    assert looks_like_a_lead("Conversion")


def test_a_label_is_proposed_so_the_field_is_never_blank():
    assert suggested_label("form_submission") == "Form Submission"
    assert suggested_label("Phone Call / Email Click") == "Phone Call Email Click"
    assert suggested_label("") == "Lead"


def _event(client_id, name, when, url, count=5):
    return FactGa4Event(
        id=uuid4(),
        client_id=client_id,
        date=when,
        raw_url=url,
        normalized_url=url,
        session_source="google",
        session_medium="organic",
        channel=OrganicChannel.ORGANIC_SEARCH,
        event_name=name,
        event_count=count,
    )


def test_every_event_reaches_the_screen(db, client_a):
    """Including the ones no pattern recognises. A suggestion is a guess
    about words; hiding what it did not match would make the guess the
    decision."""
    today = date.today()
    db.add_all(
        [
            _event(client_a.id, "form_submission", today, "https://x/contact"),
            _event(client_a.id, "pdf_download", today, "https://x/asset"),
            _event(client_a.id, "page_view", today, "https://x/"),
        ]
    )
    db.commit()

    rows = {c.event_name: c for c in load_event_candidates(db, client_a.id, today=today)}
    assert set(rows) == {"form_submission", "pdf_download", "page_view"}
    assert rows["form_submission"].suggested is True
    assert rows["pdf_download"].suggested is False
    assert rows["page_view"].automatic is True


def test_the_page_count_separates_a_lead_from_a_pageview(db, client_a):
    """The sharpest signal on the screen. A lead event fires on a handful of
    pages; `page_view` fires on all of them."""
    today = date.today()
    db.add_all(
        [_event(client_a.id, "page_view", today, f"https://x/p{i}") for i in range(12)]
        + [_event(client_a.id, "form_submission", today, "https://x/contact")]
    )
    db.commit()

    rows = {c.event_name: c for c in load_event_candidates(db, client_a.id, today=today)}
    assert rows["page_view"].pages == 12
    assert rows["form_submission"].pages == 1


def test_an_event_that_stopped_firing_does_not_count(db, client_a):
    """All-time totals flatter an event that went quiet months ago, which is
    the opposite of what the reader needs."""
    today = date.today()
    db.add(_event(client_a.id, "form_submission", today - timedelta(days=200), "https://x/c"))
    db.commit()

    rows = {c.event_name: c for c in load_event_candidates(db, client_a.id, today=today)}
    assert "form_submission" not in rows


def test_a_defined_event_that_went_quiet_still_appears(db, client_a):
    """Otherwise saving the screen would silently drop the client's own
    existing definition."""
    today = date.today()
    db.add(
        ConversionDefinition(
            client_id=client_a.id,
            event_name="old_form",
            conversion_name="Old form",
            conversion_type="lead",
            is_primary=True,
            active=True,
        )
    )
    db.commit()

    rows = {c.event_name: c for c in load_event_candidates(db, client_a.id, today=today)}
    assert rows["old_form"].defined is True
    assert rows["old_form"].is_primary is True
    assert rows["old_form"].event_count == 0


def test_defined_first_then_suggested_then_the_rest(db, client_a):
    """The order is the decision: what is already set, what looks like a
    lead, then everything else by volume."""
    today = date.today()
    db.add_all(
        [
            _event(client_a.id, "page_view", today, "https://x/", count=9999),
            _event(client_a.id, "phone_call", today, "https://x/c", count=3),
            _event(client_a.id, "already_set", today, "https://x/c", count=1),
        ]
    )
    db.add(
        ConversionDefinition(
            client_id=client_a.id,
            event_name="already_set",
            conversion_name="Already set",
            conversion_type="lead",
            is_primary=True,
            active=True,
        )
    )
    db.commit()

    order = [c.event_name for c in load_event_candidates(db, client_a.id, today=today)]
    assert order[0] == "already_set"
    assert order.index("phone_call") < order.index("page_view")


def test_the_automatic_list_covers_what_ga4_sends_itself():
    """A short list that has to stay honest: everything in it is collected
    by GA4 without anyone asking, so none of it is a lead."""
    for name in ("page_view", "session_start", "scroll", "form_start"):
        assert name in AUTOMATIC_EVENTS
    assert "form_submission" not in AUTOMATIC_EVENTS
