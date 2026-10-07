"""One rule for what a client is buying.

There were four implementations: this module, which nothing called; the
web's own copy, which the UI used; and open-coded versions in
`app.action_plan` and `app.readiness_report`. The two CLIs honoured a
client's custom override on every tier rather than only on Enterprise,
and had no fallback for a tier with no `growth_action_allowance`, so the
command used to verify a plan could print a different number from the
screen the client was shown.

No client happened to be configured in a way that made them disagree,
which is why nothing caught it.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.client import Tier
from app.services.plan_allowances import is_enterprise_tier, resolve_plan_allowances


def _tier(db, **overrides) -> Tier:
    row = Tier(
        id=uuid.uuid4(),
        tier_name=overrides.pop("tier_name", f"Tier-{uuid.uuid4().hex[:8]}"),
        tracked_keyword_limit=100,
        tracked_prompt_limit=50,
        content_allowance=3,
        update_allowance=3,
        growth_action_allowance=overrides.pop("growth_action_allowance", 1),
        watchlist_cadence="monthly",
        conversion_limit=3,
        reporting_level=overrides.pop("reporting_level", "launch"),
        **overrides,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ── Whose override counts ──


def test_a_non_enterprise_override_is_ignored(db, client_a, tier):
    """The CLIs honoured this and the screen did not. Enterprise is the
    tier the agency sets by hand; on every other plan the tier is the
    product, and a stray override must not quietly change what is sold."""
    client_a.custom_growth_action_allowance = 9
    db.commit()
    assert resolve_plan_allowances(client_a, tier).growth_action_allowance == 1


def test_an_enterprise_override_is_honoured(db, client_a):
    enterprise = _tier(db, tier_name="Enterprise", reporting_level="enterprise")
    client_a.custom_growth_action_allowance = 8
    db.commit()
    assert resolve_plan_allowances(client_a, enterprise).growth_action_allowance == 8


def test_enterprise_with_no_override_falls_back_to_the_tier(db, client_a):
    enterprise = _tier(db, tier_name="Enterprise", reporting_level="enterprise")
    client_a.custom_growth_action_allowance = None
    db.commit()
    assert resolve_plan_allowances(client_a, enterprise).growth_action_allowance == 1


def test_either_the_name_or_the_reporting_level_makes_it_enterprise(db):
    assert is_enterprise_tier(_tier(db, tier_name="Enterprise"))
    assert is_enterprise_tier(_tier(db, reporting_level="enterprise"))
    assert not is_enterprise_tier(_tier(db, tier_name="Lift"))
    assert not is_enterprise_tier(None)


def test_the_name_is_matched_whatever_its_case(db):
    """The web compared it exactly and this module lower-cased it. A tier
    seeded as ENTERPRISE would have been custom in one and not the other."""
    assert is_enterprise_tier(_tier(db, tier_name="ENTERPRISE"))


# ── A tier that predates growth actions ──


def test_a_tier_set_to_zero_growth_actions_means_zero(db, client_a):
    """The web carried a `?? update_allowance` fallback here. The column is
    NOT NULL defaulting to 0 and the API types it as a plain int, so that
    fallback could never fire — and porting it to the server would have
    turned a tier deliberately sold with no growth actions into one with
    three."""
    none_included = _tier(db, growth_action_allowance=0)
    assert none_included.update_allowance == 3
    assert resolve_plan_allowances(client_a, none_included).growth_action_allowance == 0


def test_a_client_with_no_tier_at_all_is_an_error_not_a_zero(db, client_a):
    client_a.tier_id = None
    with pytest.raises(ValueError):
        resolve_plan_allowances(client_a, None)


# ── What the API serves ──


def test_the_client_payload_carries_the_resolved_allowance(db, client_a, tier):
    """So the web never applies the rule itself — and never has to read the
    admin tier list to do it, which a client-role user cannot fetch."""
    from app.api.routers.clients import client_out

    out = client_out(client_a)
    assert out.growth_action_allowance == 1
    assert out.plan_label == f"{tier.tier_name} plan"
