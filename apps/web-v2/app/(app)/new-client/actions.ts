"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch, type Client } from "@/lib/api";

export type CreateResult = { ok: true; slug: string } | { ok: false; error: string };

export async function createClientAction(fields: Record<string, unknown>): Promise<CreateResult> {
  try {
    const created = await apiFetch<Client>("/clients", { method: "POST", body: fields });
    revalidatePath("/", "layout");
    return { ok: true, slug: created.slug };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof ApiError ? error.message : "Could not add the client: the API did not answer.",
    };
  }
}

export type SiteResult = { line: string; ok: boolean; slug?: string; error?: string };

/** One client per site, all in the same group, made one after another so a bad line does not stop the rest. */
export async function createSitesAction(group: string, mode: "execution" | "consulting", sites: { name: string; domain: string }[], tierId: string | null): Promise<SiteResult[]> {
  const out: SiteResult[] = [];
  for (const site of sites) {
    try {
      const created = await apiFetch<Client>("/clients", {
        method: "POST",
        body: { client_name: site.name, domain: site.domain, group_name: group || null, service_mode: mode, tier_id: mode === "consulting" ? null : tierId, service_reporting: { organiciq: true, ad_accelerator: false } },
      });
      out.push({ line: `${site.name} (${site.domain})`, ok: true, slug: created.slug });
    } catch (error) {
      out.push({ line: `${site.name} (${site.domain})`, ok: false, error: error instanceof ApiError ? error.message : "The API did not answer." });
    }
  }
  revalidatePath("/", "layout");
  return out;
}
