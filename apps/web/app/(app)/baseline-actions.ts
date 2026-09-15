"use server";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/api";

export type BaselineSnapshotPreview = {
  ready: boolean;
  window: {
    from: string;
    to: string;
    period_days: number;
    scaled_to_days: number;
    /** What was asked for, so partial coverage is visible. */
    requested_from: string;
    requested_days: number;
    fully_covered: boolean;
  };
  lead_events: string[];
  tier_name: string | null;
  plan: string;
  plan_label: string;
  period_sessions: number;
  period_leads: number;
  baseline_as_of: string;
  baseline_monthly_sessions: number;
  baseline_monthly_leads: number;
  baseline_lead_rate_pct: number | null;
  baseline_source: string;
  suggested_monthly_lead_goal: number;
  goal_horizon_months: number;
  checkpoints: Array<{
    label: string;
    month: number;
    monthly_sessions: number;
    lead_rate_pct: number;
    monthly_leads: number;
  }>;
  disclaimer: string;
  current_monthly_lead_goal: number | null;
  applied_monthly_lead_goal?: number | null;
  projection_generated_on?: string | null;
};

export type BaselineProjection = {
  generated_on: string;
  baseline_as_of: string;
  window: BaselineSnapshotPreview["window"];
  plan: string;
  plan_label: string;
  goal_horizon_months: number;
  suggested_monthly_lead_goal: number;
  checkpoints: BaselineSnapshotPreview["checkpoints"];
};

export async function previewBaselineFromGa4Action(
  clientId: string,
  options: { asOf?: string | null; lookbackDays?: number } = {},
) {
  if (!clientId) return { ok: false as const, error: "Missing client" };
  const params = new URLSearchParams();
  if (options.asOf) params.set("as_of", options.asOf);
  params.set("lookback_days", String(options.lookbackDays ?? 90));
  try {
    const preview = await apiFetch<BaselineSnapshotPreview>(
      `/clients/${clientId}/baseline/preview?${params.toString()}`,
      { clientId },
    );
    return { ok: true as const, preview };
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "Failed to preview baseline",
    };
  }
}

export async function applyBaselineFromGa4Action(formData: FormData) {
  const clientId = String(formData.get("clientId") || "");
  if (!clientId) return { ok: false as const, error: "Missing client" };

  const goalRaw = String(formData.get("monthly_lead_goal") || "").trim();
  const goal = goalRaw === "" ? null : Number(goalRaw);
  if (goal != null && (Number.isNaN(goal) || goal < 0)) {
    return { ok: false as const, error: "Monthly lead goal must be a non-negative number." };
  }

  try {
    const preview = await apiFetch<BaselineSnapshotPreview>(
      `/clients/${clientId}/baseline/from-ga4`,
      {
        method: "POST",
        clientId,
        body: {
          monthly_lead_goal: goal,
          notes: String(formData.get("notes") || "").trim() || null,
          as_of: String(formData.get("as_of") || "").trim() || null,
          lookback_days: Number(formData.get("lookback_days") || 90),
        },
      },
    );
    revalidatePath("/clients", "layout");
    revalidatePath("/dashboard");
    return { ok: true as const, preview };
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "Failed to apply baseline snapshot",
    };
  }
}
