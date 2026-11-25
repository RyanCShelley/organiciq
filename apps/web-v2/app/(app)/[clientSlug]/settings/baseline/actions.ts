"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import { invalidateClientsCache } from "@/lib/clients";
import type {
  Analysis,
  AnalysisResult,
  BaselineGoalState,
  BaselineLockResponse,
  PillarsSnapshot,
} from "@/lib/baseline";

function message(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export async function loadBaselineAction(
  clientId: string,
  events: string[],
  regimeStart: string,
  acknowledged: string[],
  months = 24,
  halfLifeMonths = 3,
): Promise<AnalysisResult> {
  const params = new URLSearchParams({
    months: String(months),
    half_life_months: String(halfLifeMonths),
  });
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

export async function loadBaselineCsvAction(
  clientId: string,
  csvText: string,
  regimeStart: string,
  acknowledged: string[],
  halfLifeMonths = 3,
): Promise<AnalysisResult> {
  try {
    const analysis = await apiFetch<Analysis>(`/clients/${clientId}/baseline/series`, {
      method: "POST",
      body: {
        csv_text: csvText,
        regime_start: regimeStart || null,
        half_life_months: halfLifeMonths,
        acknowledged,
      },
    });
    return { ok: true, analysis };
  } catch (error) {
    return { ok: false, error: message(error, "Could not analyze CSV baseline.") };
  }
}

export async function lockBaselineAction(
  clientId: string,
  slug: string,
  body: {
    source?: "ga4" | "csv";
    csv_text?: string | null;
    months?: number;
    half_life_months?: number;
    lead_events: string[];
    regime_start: string | null;
    acknowledged: string[];
    reason_code: string | null;
    reason_note: string | null;
    monthly_lead_goal: number | null;
    monthly_traffic_goal?: number | null;
    monthly_visibility_clicks_goal?: number | null;
    ai_visibility_pct_goal?: number | null;
    target_lead_rate_pct?: number | null;
    sync_lead_conversions: boolean;
  },
): Promise<{ ok: true; data: BaselineLockResponse } | { ok: false; error: string }> {
  try {
    const data = await apiFetch<BaselineLockResponse>(`/clients/${clientId}/baseline/lock`, {
      method: "POST",
      body: {
        source: body.source ?? "ga4",
        months: body.months ?? 24,
        half_life_months: body.half_life_months ?? 3,
        ...body,
      },
    });
    invalidateClientsCache();
    revalidatePath("/");
    revalidatePath(`/${slug}/settings/baseline`);
    revalidatePath(`/${slug}`, "layout");
    return { ok: true, data };
  } catch (error) {
    return { ok: false, error: message(error, "The baseline could not be locked: the API did not answer.") };
  }
}

export async function updateBaselineGoalAction(
  clientId: string,
  slug: string,
  monthlyLeadGoal: number,
  pillarGoals?: {
    monthly_traffic_goal?: number | null;
    monthly_visibility_clicks_goal?: number | null;
    ai_visibility_pct_goal?: number | null;
  },
): Promise<{ ok: true; goal: BaselineGoalState } | { ok: false; error: string }> {
  try {
    const goal = await apiFetch<BaselineGoalState>(`/clients/${clientId}/baseline/goal`, {
      method: "POST",
      body: { monthly_lead_goal: monthlyLeadGoal, ...(pillarGoals ?? {}) },
    });
    invalidateClientsCache();
    revalidatePath("/");
    revalidatePath(`/${slug}/settings/baseline`);
    revalidatePath(`/${slug}`, "layout");
    return { ok: true, goal };
  } catch (error) {
    return { ok: false, error: message(error, "Could not update the monthly goal.") };
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
