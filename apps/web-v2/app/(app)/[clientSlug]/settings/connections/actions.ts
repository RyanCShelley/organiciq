"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { ActionResult } from "@/lib/client-settings";
import type { AdsDiagnosis, AdsPullResult, ConnectResult, OptionsResult } from "@/lib/connections";

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

/** After a source is chosen or changed, pull what it feeds. Best effort: the save already worked, so a failure here is not reported as one. */
async function pullAfterSave(clientId: string, slug: string, sources: string[], previous: string | null, chosen: string): Promise<void> {
  if (previous === chosen) return;
  try {
    await apiFetch("/v2/connections/pull", { method: "POST", clientId, body: { sources } });
    revalidatePath(`/${slug}/settings/connections`);
  } catch {
    /* the Pull data button is still there */
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

export async function saveGscAction(clientId: string, slug: string, siteUrl: string, previous: string | null = null): Promise<ActionResult> {
  const result = await save(slug, "/integrations/gsc/property", clientId, { site_url: siteUrl, role: "primary" });
  if (result.ok) await pullAfterSave(clientId, slug, ["gsc_pages", "gsc_queries"], previous, siteUrl);
  return result;
}

export async function loadGa4Action(clientId: string): Promise<OptionsResult> {
  return options<{ property_id: string; display_name: string; account_name: string }>(
    "/integrations/ga4/properties",
    clientId,
    (r) => ({ value: r.property_id, label: `${r.display_name} · ${r.account_name} (${r.property_id})` }),
  );
}

export async function saveGa4Action(clientId: string, slug: string, propertyId: string, previous: string | null = null): Promise<ActionResult> {
  const result = await save(slug, "/integrations/ga4/property", clientId, { property_id: propertyId });
  const normalized = propertyId.startsWith("properties/") ? propertyId : `properties/${propertyId}`;
  if (result.ok) await pullAfterSave(clientId, slug, ["ga4"], previous, normalized);
  return result;
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
  previous: string | null = null,
): Promise<ActionResult> {
  const result = await save(slug, "/integrations/seranking/property", clientId, { site_id: siteId, project_name: name });
  if (result.ok) await pullAfterSave(clientId, slug, ["se_ranking_search", "se_ranking_ai"], previous, siteId);
  return result;
}

export async function loadBingSitesAction(clientId: string): Promise<OptionsResult> {
  return options<{ url: string; verified: boolean }>("/v2/connections/bing/sites", clientId, (r) => ({
    value: r.url,
    label: r.verified ? r.url : `${r.url} (not verified)`,
  }));
}

export async function saveBingAction(clientId: string, slug: string, siteUrl: string, previous: string | null = null): Promise<ActionResult> {
  const result = await save(slug, "/v2/connections/bing", clientId, { site_url: siteUrl }, "PUT");
  if (result.ok) await pullAfterSave(clientId, slug, ["bing_query_stats"], previous, siteUrl);
  return result;
}

export async function clearBingAction(clientId: string, slug: string): Promise<ActionResult> {
  return save(slug, "/v2/connections/bing", clientId, undefined, "DELETE");
}

/** The projects the token can see, found from its tasklists (a project is what content lists are made in). */
export async function loadTeamworkProjectsAction(clientId: string): Promise<OptionsResult> {
  try {
    const res = await apiFetch<{
      configured: boolean;
      error: string | null;
      tasklists: { id: string; name: string; project_id: string | null; project_name: string | null }[];
    }>("/decisions/teamwork/tasklists", { clientId });
    if (!res.configured) return { ok: false, error: "Teamwork is not set up on this install." };
    if (res.error) return { ok: false, error: res.error };
    const seen = new Map<string, string>();
    for (const t of res.tasklists) if (t.project_id && !seen.has(t.project_id)) seen.set(t.project_id, t.project_name ?? `Project ${t.project_id}`);
    return { ok: true, options: Array.from(seen, ([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label)) };
  } catch (error) {
    return { ok: false, error: error instanceof ApiError ? error.message : "The projects could not be read: the API did not answer." };
  }
}

export async function loadTeamworkTasklistsAction(clientId: string): Promise<OptionsResult> {
  try {
    const res = await apiFetch<{
      configured: boolean;
      error: string | null;
      tasklists: { id: string; name: string; project_name: string | null }[];
    }>("/decisions/teamwork/tasklists", { clientId });
    if (!res.configured) return { ok: false, error: "Teamwork is not set up on this install." };
    if (res.error) return { ok: false, error: res.error };
    return {
      ok: true,
      options: res.tasklists.map((t) => ({
        value: t.id,
        label: t.project_name ? `${t.project_name} · ${t.name}` : t.name,
      })),
    };
  } catch (error) {
    return { ok: false, error: message(error, DID_NOT_ANSWER) };
  }
}

export async function loadAdsAccountsAction(taken: string[]): Promise<OptionsResult> {
  try {
    const r = await apiFetch<{ accounts: { id: string; name: string }[] }>("/v2/ads/available");
    return {
      ok: true,
      options: r.accounts.filter((a) => !taken.includes(a.id)).map((a) => ({ value: a.id, label: `${a.name} (${a.id.replace(/^(\d{3})(\d{3})(\d{4})$/, "$1-$2-$3")})` })),
    };
  } catch (error) {
    return { ok: false, error: message(error, DID_NOT_ANSWER) };
  }
}

/** Add a Google Ads account to the client, then pull so the pages have numbers. The save worked even when the pull did not. */
export async function addAdsAccountAction(clientId: string, slug: string, customerId: string, name: string, kind: "ads" | "lsa"): Promise<ActionResult> {
  const result = await save(slug, "/v2/ads/accounts", clientId, { customer_id: customerId, name, kind });
  if (result.ok) {
    try {
      await apiFetch("/v2/ads/pull", { method: "POST", clientId });
    } catch {
      /* the connection card shows why the pull failed */
    }
    revalidatePath(`/${slug}/settings/connections`);
    revalidatePath(`/${slug}/ads`);
  }
  return result;
}

export async function removeAdsAccountAction(clientId: string, slug: string, customerId: string): Promise<ActionResult> {
  const result = await save(slug, `/v2/ads/accounts/${customerId}`, clientId, undefined, "DELETE");
  revalidatePath(`/${slug}/ads`);
  return result;
}

/** Change an account's kind or name without pulling. */
export async function updateAdsAccountAction(clientId: string, slug: string, customerId: string, name: string, kind: "ads" | "lsa"): Promise<ActionResult> {
  return save(slug, "/v2/ads/accounts", clientId, { customer_id: customerId, name, kind });
}

export async function pullAdsAction(clientId: string, slug: string): Promise<{ ok: true; data: AdsPullResult } | { ok: false; error: string }> {
  try {
    const data = await apiFetch<AdsPullResult>("/v2/ads/pull", { method: "POST", clientId });
    return { ok: true, data };
  } catch (error) {
    return { ok: false, error: message(error, DID_NOT_ANSWER) };
  } finally {
    revalidatePath(`/${slug}/settings/connections`);
    revalidatePath(`/${slug}/ads`);
  }
}

/** Ask Google Ads, account by account, what it returns: what works, what is empty, what is refused. Read-only; nothing is stored. */
export async function diagnoseAdsAction(clientId: string): Promise<{ ok: true; data: AdsDiagnosis } | { ok: false; error: string }> {
  try {
    return { ok: true, data: await apiFetch<AdsDiagnosis>("/v2/ads/diagnose", { method: "POST", clientId }) };
  } catch (error) {
    return { ok: false, error: message(error, DID_NOT_ANSWER) };
  }
}
