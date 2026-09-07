import type { Client, Tier } from "@/lib/api";

export type PlanAllowances = {
  tierName: string;
  isCustom: boolean;
  trackedKeywordLimit: number;
  trackedPromptLimit: number;
  contentAllowance: number;
  updateAllowance: number;
  growthActionAllowance: number;
  watchlistCadence: string;
};

export function isEnterpriseTier(tier: Tier | null | undefined): boolean {
  if (!tier) return false;
  return tier.tier_name === "Enterprise" || tier.reporting_level === "enterprise";
}

export function resolvePlanAllowances(client: Client, tier: Tier | null | undefined): PlanAllowances {
  const isCustom = isEnterpriseTier(tier);
  const pickInt = (customValue: number | null | undefined, tierValue: number | undefined) => {
    if (isCustom && customValue != null) return customValue;
    return tierValue ?? 0;
  };
  const pickStr = (customValue: string | null | undefined, tierValue: string | undefined) => {
    if (isCustom && customValue) return customValue;
    return tierValue ?? "monthly";
  };

  return {
    tierName: tier?.tier_name ?? "Unknown",
    isCustom,
    trackedKeywordLimit: pickInt(client.custom_tracked_keyword_limit, tier?.tracked_keyword_limit),
    trackedPromptLimit: pickInt(client.custom_tracked_prompt_limit, tier?.tracked_prompt_limit),
    contentAllowance: pickInt(client.custom_content_allowance, tier?.content_allowance),
    updateAllowance: pickInt(client.custom_update_allowance, tier?.update_allowance),
    growthActionAllowance: pickInt(
      client.custom_growth_action_allowance,
      tier?.growth_action_allowance ?? tier?.update_allowance,
    ),
    watchlistCadence: pickStr(client.custom_watchlist_cadence, tier?.watchlist_cadence),
  };
}
