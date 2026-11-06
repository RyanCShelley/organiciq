import { cache } from "react";

import { apiFetch } from "@/lib/api";

/** A site as the portal shows it: name and address only, never its plan or connections. */
export type PortalSite = { id: string; slug: string; name: string; domain: string; group: string | null };
export type PortalHome = { client: PortalSite; sites: PortalSite[]; brand: { name: string; powered_by: string }; previewing: boolean };

/** The portals this person may open. */
export const getPortals = cache(async () => apiFetch<{ clients: PortalSite[]; is_staff: boolean }>("/v2/consulting/clients"));

export type Profile = {
  goals: string | null;
  primary_objective: string | null;
  audiences: string | null;
  markets: string | null;
  priority_services: string | null;
  constraints: string | null;
  editorial_rules: string | null;
  resources: string | null;
  internal_notes: string | null;
  updated_by: string | null;
  updated_at: string | null;
};
