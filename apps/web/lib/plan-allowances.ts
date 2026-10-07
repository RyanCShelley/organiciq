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

/**
 * A preview of what the server will decide, for the settings form only.
 *
 * `app/services/plan_allowances.py` is authoritative and every read path
 * takes its answer from the API. This copy exists because the settings
 * form shows the effect of a tier the user has picked but not yet saved,
 * so there is nothing to ask the server about. It must match the server
 * exactly; where the two drifted, the CLI that verified a plan printed a
 * different number from the screen the client was shown.
 */
export function isEnterpriseTier(tier: Tier | null | undefined): boolean {
  if (!tier) return false;
  // Case-insensitive, as the server is. Compared exactly here, a tier
  // seeded as "ENTERPRISE" was custom on one side and not the other.
  return tier.tier_name?.toLowerCase() === "enterprise" || tier.reporting_level === "enterprise";
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
    // No `?? update_allowance` fallback: the column is NOT NULL with a
    // default of 0 and the API types it as a plain int, so the fallback
    // could never fire — and if it ever did it would turn a tier sold with
    // no growth actions into one with three.
    growthActionAllowance: pickInt(
      client.custom_growth_action_allowance,
      tier?.growth_action_allowance,
    ),
    watchlistCadence: pickStr(client.custom_watchlist_cadence, tier?.watchlist_cadence),
  };
}
