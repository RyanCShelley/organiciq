"use server";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/api";

// --- Baseline calculator (recent window, ranges, flags, locked versions) ----

export type BaselineFlag = {
  code: string;
  level: "blocker" | "warning" | "info";
  message: string;
  months: string[];
  acknowledged: boolean;
};

export type BaselineBand = { low: number; high: number; pct: number };

export type BaselineSeriesRow = {
  month: string;
  sessions: number;
  organic_sessions: number | null;
  leads: number;
  lead_rate_pct: number | null;
  in_window: boolean;
  by_event: Record<string, number>;
};

export type BaselineCheckpoint = {
  label: string;
  month: number;
  monthly_sessions: number;
  lead_rate_pct: number;
  monthly_leads: number;
};

export type BaselineSeriesResult = {
  method_version: string;
  status: "draft" | "provisional";
  window: {
    from: string;
    to: string;
    months: number;
    regime_start: string | null;
    regime_start_source: "given" | "none";
    suggested_regime_start: string | null;
  };
  baseline: {
    monthly_sessions: number;
    monthly_organic_sessions: number | null;
    lead_rate_pct: number;
    monthly_leads: number;
  };
  ranges: {
    monthly_sessions: BaselineBand;
    monthly_organic_sessions: BaselineBand | null;
    lead_rate_pct: BaselineBand;
    monthly_leads: BaselineBand;
  };
  goal_basis: { monthly_sessions: number; monthly_leads: number; lead_rate_pct: number; basis: string };
  references: {
    mean_leads_last_3_months: number;
    mean_leads_last_12_months: number;
    pooled_lead_rate_pct_window: number;
  };
  projection: { plan_label: string; suggested_monthly_lead_goal: number; checkpoints: BaselineCheckpoint[] };
  projection_point: { suggested_monthly_lead_goal: number; checkpoints: BaselineCheckpoint[] };
  series: BaselineSeriesRow[];
  flags: BaselineFlag[];
  blockers: string[];
  can_lock: boolean;
  source: { type: "ga4" | "csv"; lead_events?: string[]; notes?: string[]; skipped_rows?: string[] };
};

export type BaselineEventCandidates = {
  events: { name: string; total: number; first_month: string; last_month: string }[];
  /** The events the rest of the tool counts as leads: the home screen, alerts and results. */
  defaults: string[];
  /** What the newest locked baseline counted. */
  locked: { version: number; events: string[] } | null;
  goal: { current: number | null; suggested: number | null; version: number | null };
};

export type BaselineVersionRow = {
  version: number;
  status: string;
  reason_code: string;
  reason_note: string | null;
  locked_by: string;
  locked_at: string | null;
  regime_start: string | null;
  window_from: string;
  window_to: string;
  lead_events: string[];
  source_type: string;
  monthly_sessions: number | null;
  monthly_organic_sessions: number | null;
  lead_rate_pct: number | null;
  monthly_leads: number | null;
  goal_monthly_leads: number | null;
};

export type BaselineSeriesInput = {
  source: "ga4" | "csv";
  csvText?: string;
  regimeStart?: string;
  leadEvents?: string[];
  halfLifeMonths?: number;
  acknowledged?: string[];
};

function fail(e: unknown, fallback: string) {
  return { ok: false as const, error: e instanceof Error ? e.message : fallback };
}

export async function fetchBaselineSeriesAction(clientId: string, input: BaselineSeriesInput) {
  if (!clientId) return { ok: false as const, error: "Missing client" };
  try {
    if (input.source === "csv") {
      const result = await apiFetch<BaselineSeriesResult>(`/clients/${clientId}/baseline/series`, {
        method: "POST",
        clientId,
        body: {
          csv_text: input.csvText ?? "",
          regime_start: input.regimeStart || null,
          half_life_months: input.halfLifeMonths ?? 3,
          acknowledged: input.acknowledged ?? [],
        },
      });
      return { ok: true as const, result };
    }
    const params = new URLSearchParams();
    if (input.regimeStart) params.set("regime_start", input.regimeStart);
    params.set("half_life_months", String(input.halfLifeMonths ?? 3));
    for (const name of input.leadEvents ?? []) params.append("lead_event", name);
    for (const code of input.acknowledged ?? []) params.append("acknowledge", code);
    const result = await apiFetch<BaselineSeriesResult>(
      `/clients/${clientId}/baseline/series?${params.toString()}`,
      { clientId },
    );
    return { ok: true as const, result };
  } catch (e) {
    return fail(e, "Could not build the baseline");
  }
}

export async function listBaselineEventsAction(clientId: string) {
  try {
    const events = await apiFetch<BaselineEventCandidates>(`/clients/${clientId}/baseline/events`, { clientId });
    return { ok: true as const, events };
  } catch (e) {
    return fail(e, "Could not list the events");
  }
}

export async function listBaselineVersionsAction(clientId: string) {
  try {
    const versions = await apiFetch<BaselineVersionRow[]>(`/clients/${clientId}/baseline/versions`, { clientId });
    return { ok: true as const, versions };
  } catch (e) {
    return fail(e, "Could not load the baseline versions");
  }
}

export async function lockBaselineAction(
  clientId: string,
  input: BaselineSeriesInput & {
    reasonCode?: string;
    reasonNote?: string;
    monthlyLeadGoal?: number | null;
    syncLeadConversions?: boolean;
  },
) {
  if (!clientId) return { ok: false as const, error: "Missing client" };
  try {
    const locked = await apiFetch<{
      version: BaselineVersionRow;
      lead_conversions_changed: { add: string[]; remove: string[]; keep: string[] } | null;
      monthly_lead_goal: number | null;
      suggested_monthly_lead_goal: number;
      goal_set_by_lock: boolean;
    }>(`/clients/${clientId}/baseline/lock`, {
      method: "POST",
      clientId,
      body: {
        source: input.source,
        csv_text: input.source === "csv" ? (input.csvText ?? "") : null,
        regime_start: input.regimeStart || null,
        lead_events: input.leadEvents ?? [],
        half_life_months: input.halfLifeMonths ?? 3,
        acknowledged: input.acknowledged ?? [],
        reason_code: input.reasonCode || null,
        reason_note: input.reasonNote || null,
        monthly_lead_goal: input.monthlyLeadGoal ?? null,
        sync_lead_conversions: input.syncLeadConversions ?? false,
      },
    });
    revalidatePath("/clients", "layout");
    revalidatePath("/dashboard");
    return { ok: true as const, locked };
  } catch (e) {
    return fail(e, "Could not lock the baseline");
  }
}

/** Make these exactly the client's lead conversions, so the baseline and the home screen agree. */
export async function setLeadConversionsAction(clientId: string, leadEvents: string[]) {
  try {
    const done = await apiFetch<{ changes: { add: string[]; remove: string[] }; lead_events: string[] }>(
      `/clients/${clientId}/baseline/lead-conversions`,
      { method: "POST", clientId, body: { lead_events: leadEvents } },
    );
    revalidatePath("/clients", "layout");
    revalidatePath("/dashboard");
    return { ok: true as const, done };
  } catch (e) {
    return fail(e, "Could not update the lead conversions");
  }
}

/** Set the plan-end monthly lead goal, e.g. to the newest locked baseline's 12-month figure. */
export async function setBaselineGoalAction(clientId: string, monthlyLeadGoal: number) {
  try {
    await apiFetch(`/clients/${clientId}/baseline/goal`, {
      method: "POST",
      clientId,
      body: { monthly_lead_goal: monthlyLeadGoal },
    });
    revalidatePath("/clients", "layout");
    revalidatePath("/dashboard");
    return { ok: true as const };
  } catch (e) {
    return fail(e, "Could not update the goal");
  }
}

// --- Reset every client's baseline and goals (admin) -------------------------

export type BaselineResetPreview = {
  clients: {
    client_id: string;
    slug: string;
    client_name: string;
    versions: number;
    has_baseline: boolean;
    baseline_as_of: string | null;
    monthly_lead_goal: number | null;
    goal_corrections: number;
  }[];
  totals: { clients: number; versions: number };
};

export async function previewBaselineResetAction() {
  try {
    const preview = await apiFetch<BaselineResetPreview>("/admin/baselines/reset-preview");
    return { ok: true as const, preview };
  } catch (e) {
    return fail(e, "Could not check what a reset would clear");
  }
}

export async function resetBaselinesAction(confirm: string) {
  try {
    const done = await apiFetch<{ reset_clients: number; versions_deleted: number; removed: unknown[] }>(
      "/admin/baselines/reset",
      { method: "POST", body: { confirm } },
    );
    revalidatePath("/clients", "layout");
    revalidatePath("/dashboard");
    return { ok: true as const, done };
  } catch (e) {
    return fail(e, "The reset did not run");
  }
}
