"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { ActionResult } from "@/lib/client-settings";
import type { ConnectResult, OptionsResult } from "@/lib/connections";

function message(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

const DID_NOT_ANSWER = "The API did not answer.";

async function options<T>(
  path: string,
  clientId: string,
  map: (row: T) => { value: string; label: string },
): Promise<OptionsResult> {
  try {
    const rows = await apiFetch<T[]>(path, { clientId });
    return { ok: true, options: rows.map(map) };
  } catch (error) {
    return { ok: false, error: message(error, DID_NOT_ANSWER) };
  }
}

async function save(
  slug: string,
  path: string,
  clientId: string,
  body: unknown,
  method = "POST",
): Promise<ActionResult> {
  try {
    await apiFetch(path, { method, body, clientId });
    revalidatePath(`/${slug}/settings/connections`);
    return { ok: true };
  } catch (error) {
    return { ok: false, error: message(error, DID_NOT_ANSWER) };
  }
}

export async function startGoogleConnectAction(clientId: string): Promise<ConnectResult> {
  try {
    const res = await apiFetch<{ authorization_url: string }>(
      `/oauth/google/start?client_id=${clientId}&return_to=v2`,
    );
    return { ok: true, url: res.authorization_url };
  } catch (error) {
    return { ok: false, error: message(error, DID_NOT_ANSWER) };
  }
}

export async function loadGscSitesAction(clientId: string): Promise<OptionsResult> {
  return options<{ site_url: string; permission_level: string | null }>(
    "/integrations/gsc/sites",
    clientId,
    (r) => ({ value: r.site_url, label: r.site_url }),
  );
}

export async function saveGscAction(clientId: string, slug: string, siteUrl: string): Promise<ActionResult> {
  return save(slug, "/integrations/gsc/property", clientId, { site_url: siteUrl, role: "primary" });
}

export async function loadGa4Action(clientId: string): Promise<OptionsResult> {
  return options<{ property_id: string; display_name: string; account_name: string }>(
    "/integrations/ga4/properties",
    clientId,
    (r) => ({ value: r.property_id, label: `${r.display_name} · ${r.account_name} (${r.property_id})` }),
  );
}

export async function saveGa4Action(clientId: string, slug: string, propertyId: string): Promise<ActionResult> {
  return save(slug, "/integrations/ga4/property", clientId, { property_id: propertyId });
}

export async function loadSeRankingAction(clientId: string): Promise<OptionsResult> {
  return options<{ site_id: string; title: string; url: string | null }>(
    "/integrations/seranking/projects",
    clientId,
    (r) => ({ value: r.site_id, label: r.url ? `${r.title} · ${r.url}` : r.title }),
  );
}

export async function saveSeRankingAction(
  clientId: string,
  slug: string,
  siteId: string,
  name: string,
): Promise<ActionResult> {
  return save(slug, "/integrations/seranking/property", clientId, { site_id: siteId, project_name: name });
}

export async function loadBingSitesAction(clientId: string): Promise<OptionsResult> {
  return options<{ url: string; verified: boolean }>("/v2/connections/bing/sites", clientId, (r) => ({
    value: r.url,
    label: r.verified ? r.url : `${r.url} (not verified)`,
  }));
}

export async function saveBingAction(clientId: string, slug: string, siteUrl: string): Promise<ActionResult> {
  return save(slug, "/v2/connections/bing", clientId, { site_url: siteUrl }, "PUT");
}

export async function clearBingAction(clientId: string, slug: string): Promise<ActionResult> {
  return save(slug, "/v2/connections/bing", clientId, undefined, "DELETE");
}
