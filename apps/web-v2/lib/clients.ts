import { cache } from "react";

import { apiFetch, type Client } from "@/lib/api";
import { auth } from "@/lib/auth";

/** How long a screen may use the client list it already has. Short, because a name, a plan or a setting can change in another tab. */
const RECENT_MS = 20_000;
const recent = new Map<string, { at: number; clients: Client[] }>();

/** The clients this person can see, fetched once per request and always current. The shell, the home page and the settings screens use this one. */
export const getClients = cache(async () => {
  const clients = await apiFetch<Client[]>("/clients");
  const email = (await auth())?.user?.email?.toLowerCase();
  if (email) recent.set(email, { at: Date.now(), clients });
  return clients;
});

/**
 * One client by its address, for the screens that only need to know which client it is.
 *
 * Moving between screens asked the API for the whole list before each screen's own data, so every click waited on a round trip it did not need.
 * This uses the list fetched a moment ago, and asks again when the client is not in it (a new client, a renamed one) or the list has gone stale.
 * Settings screens, which show what was just edited, use `getClients` instead.
 */
export const findClient = cache(async (slug: string): Promise<Client | undefined> => {
  const email = (await auth())?.user?.email?.toLowerCase();
  const held = email ? recent.get(email) : undefined;
  if (held && Date.now() - held.at < RECENT_MS) {
    const hit = held.clients.find((c) => c.slug === slug);
    if (hit) return hit;
  }
  return (await getClients()).find((c) => c.slug === slug);
});

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
