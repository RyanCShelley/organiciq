"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { Analysis, AnalysisResult, PillarsSnapshot } from "@/lib/baseline";
import type { ActionResult } from "@/lib/client-settings";

function message(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export async function loadBaselineAction(
  clientId: string,
  events: string[],
  regimeStart: string,
  acknowledged: string[],
): Promise<AnalysisResult> {
  const params = new URLSearchParams({ months: "24" });
  for (const event of events) params.append("lead_event", event);
  for (const code of acknowledged) params.append("acknowledge", code);
  if (regimeStart) params.set("regime_start", regimeStart);
  try {
    const analysis = await apiFetch<Analysis>(`/clients/${clientId}/baseline/series?${params}`);
    return { ok: true, analysis };
  } catch (error) {
    return { ok: false, error: message(error, "The baseline could not be worked out: the API did not answer.") };
  }
}

export async function lockBaselineAction(
  clientId: string,
  slug: string,
  body: {
    lead_events: string[];
    regime_start: string | null;
    acknowledged: string[];
    reason_code: string | null;
    reason_note: string | null;
    monthly_lead_goal: number | null;
    sync_lead_conversions: boolean;
  },
): Promise<ActionResult> {
  try {
    await apiFetch(`/clients/${clientId}/baseline/lock`, {
      method: "POST",
      body: { source: "ga4", months: 24, half_life_months: 3, ...body },
    });
    revalidatePath(`/${slug}/settings/baseline`);
    return { ok: true };
  } catch (error) {
    return { ok: false, error: message(error, "The baseline could not be locked: the API did not answer.") };
  }
}

export async function loadBaselinePillarsAction(
  clientId: string,
  events: string[],
): Promise<{ ok: true; pillars: PillarsSnapshot } | { ok: false; error: string }> {
  const params = new URLSearchParams();
  for (const event of events) params.append("lead_event", event);
  try {
    const pillars = await apiFetch<PillarsSnapshot>(`/clients/${clientId}/baseline/pillars?${params}`);
    return { ok: true, pillars };
  } catch (error) {
    return { ok: false, error: message(error, "Could not load 3-pillar snapshot.") };
  }
}

export async function exportBaselinePillarsCsvAction(
  clientId: string,
  events: string[],
  version?: number,
): Promise<{ ok: true; csv: string } | { ok: false; error: string }> {
  try {
    if (version != null) {
      const csv = await apiFetch<string>(`/clients/${clientId}/baseline/versions/${version}/export.csv`, {
        rawText: true,
      });
      return { ok: true, csv };
    }
    const params = new URLSearchParams();
    for (const event of events) params.append("lead_event", event);
    const csv = await apiFetch<string>(`/clients/${clientId}/baseline/pillars/export.csv?${params}`, {
      rawText: true,
    });
    return { ok: true, csv };
  } catch (error) {
    return { ok: false, error: message(error, "Could not export baseline CSV.") };
  }
}
