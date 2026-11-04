import { cache } from "react";

import { apiFetch, type Client } from "@/lib/api";

/** The clients this person can see, fetched once per request. */
export const getClients = cache(() => apiFetch<Client[]>("/clients"));

export type Tier = {
  id: string;
  tier_name: string;
  growth_action_allowance: number;
  watchlist_cadence: string;
};

/** The five plans, in the order they are sold. */
const TIER_ORDER = ["Legacy", "Launch", "Lift", "Lead", "Enterprise"];

export const getTiers = cache(async () => {
  const tiers = await apiFetch<Tier[]>("/admin/tiers");
  return [...tiers].sort(
    (a, b) => TIER_ORDER.indexOf(a.tier_name) - TIER_ORDER.indexOf(b.tier_name),
  );
});
