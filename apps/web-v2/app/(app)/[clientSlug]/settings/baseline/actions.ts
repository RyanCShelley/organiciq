"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { Analysis, AnalysisResult } from "@/lib/baseline";
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
