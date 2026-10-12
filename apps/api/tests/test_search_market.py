"""The search market picks SE Ranking's regional index, and nothing else.

As free text the field invited "Central NY" and "Palm Bay, FL" — reasonable
answers to "primary market" and matches for nothing, so the pull fell back
to the United States while the field looked filled in.
"""

from __future__ import annotations

import pytest

from app.ingestion.seranking.pipeline_domain import DEFAULT_SOURCE, resolve_source
from app.models.client import Client
from tests.conftest import client_header


@pytest.mark.parametrize(
    "market,source",
    [
        # Exactly the four the dropdown offers, spelled as it spells them.
        ("United States", "us"),
        ("United Kingdom", "uk"),
        ("Canada", "ca"),
        ("Australia", "au"),
    ],
)
def test_every_option_the_dropdown_offers_resolves(market: str, source: str):
    assert resolve_source(Client(primary_market=market)) == source


@pytest.mark.parametrize("market", ["Central NY", "Palm Bay, FL", "", None])
def test_anything_else_falls_back_rather_than_failing(market):
    # The fallback is right; what was wrong was a field that looked set.
    assert resolve_source(Client(primary_market=market)) == DEFAULT_SOURCE


def test_omitting_the_market_leaves_it_alone(client, client_a, admin_user):
    """What the dropdown's "keep what is there" option relies on.

    A value the dropdown does not offer stays selectable under a sentinel,
    and choosing it omits the field — so opening the page and saving cannot
    quietly rewrite somebody's "Palm Bay, FL" to blank.
    """
    headers = client_header(client_a.id, admin_user.email)
    client.patch(
        f"/clients/{client_a.id}", headers=headers, json={"primary_market": "Palm Bay, FL"}
    )

    # A save that does not mention the field.
    client.patch(f"/clients/{client_a.id}", headers=headers, json={"timezone": "America/Chicago"})

    after = client.get(f"/clients/{client_a.id}", headers=headers).json()
    assert after["primary_market"] == "Palm Bay, FL"
    assert after["timezone"] == "America/Chicago"


def test_sending_null_does_clear_it(client, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    client.patch(
        f"/clients/{client_a.id}", headers=headers, json={"primary_market": "Canada"}
    )
    client.patch(f"/clients/{client_a.id}", headers=headers, json={"primary_market": None})
    assert client.get(f"/clients/{client_a.id}", headers=headers).json()["primary_market"] is None
