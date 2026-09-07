"""Resolve effective plan allowances from tier + optional client overrides."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.client import Client, Tier


@dataclass(frozen=True)
class PlanAllowances:
    tier_name: str
    is_custom: bool
    tracked_keyword_limit: int
    tracked_prompt_limit: int
    content_allowance: int
    update_allowance: int
    growth_action_allowance: int
    watchlist_cadence: str
    conversion_limit: int


def is_enterprise_tier(tier: Tier | None) -> bool:
    if tier is None:
        return False
    return tier.tier_name.lower() == "enterprise" or tier.reporting_level == "enterprise"


def resolve_plan_allowances(client: Client, tier: Tier | None = None) -> PlanAllowances:
    active_tier = tier or client.tier
    if active_tier is None:
        raise ValueError("Client has no tier")

    custom = is_enterprise_tier(active_tier)

    def pick_int(custom_value: int | None, tier_value: int) -> int:
        if custom and custom_value is not None:
            return custom_value
        return tier_value

    def pick_str(custom_value: str | None, tier_value: str) -> str:
        if custom and custom_value:
            return custom_value
        return tier_value

    return PlanAllowances(
        tier_name=active_tier.tier_name,
        is_custom=custom,
        tracked_keyword_limit=pick_int(
            client.custom_tracked_keyword_limit, active_tier.tracked_keyword_limit
        ),
        tracked_prompt_limit=pick_int(
            client.custom_tracked_prompt_limit, active_tier.tracked_prompt_limit
        ),
        content_allowance=pick_int(client.custom_content_allowance, active_tier.content_allowance),
        update_allowance=pick_int(client.custom_update_allowance, active_tier.update_allowance),
        growth_action_allowance=pick_int(
            client.custom_growth_action_allowance, active_tier.growth_action_allowance
        ),
        watchlist_cadence=pick_str(
            client.custom_watchlist_cadence, active_tier.watchlist_cadence
        ),
        conversion_limit=active_tier.conversion_limit,
    )
