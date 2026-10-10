"""Running a month that is not the one we are standing in.

A month is reviewed once it has finished, so running November's engine over
October's data is the ordinary case. Before this the only month anybody could
run was the current one, measured to whatever day it happened to be — which
judged a client on three days of November and filed it as the month's plan.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.monthly_run import as_of, month_key


def test_a_finished_month_is_judged_to_its_last_day():
    # Standing in November, asking for October.
    assert as_of("2026-10", today=date(2026, 11, 4)) == date(2026, 10, 31)
    assert month_key(as_of("2026-10", today=date(2026, 11, 4))) == "2026-10"


def test_the_current_month_is_judged_to_today():
    assert as_of("2026-11", today=date(2026, 11, 4)) == date(2026, 11, 4)


def test_february_knows_about_leap_years():
    assert as_of("2024-02", today=date(2026, 1, 1)) == date(2024, 2, 29)
    assert as_of("2026-02", today=date(2026, 6, 1)) == date(2026, 2, 28)


def test_a_future_month_lands_on_today_rather_than_the_future():
    today = date(2026, 11, 4)
    assert as_of("2027-05", today=today) == today


@pytest.mark.parametrize("bad", ["2026", "2026-13", "October", "2026-1-1", ""])
def test_a_month_that_is_not_a_month_is_refused(bad: str):
    # Falling back to today would file the run under the wrong month.
    with pytest.raises(ValueError):
        as_of(bad, today=date(2026, 11, 4))


def test_the_endpoint_refuses_a_bad_month(client, client_a, admin_user):
    from tests.conftest import client_header

    response = client.post(
        "/decisions/records/run",
        headers=client_header(client_a.id, admin_user.email),
        json={"month": "2026-13"},
    )
    assert response.status_code == 422
