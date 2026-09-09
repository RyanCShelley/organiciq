"use server";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/api";

export async function createAnnotationAction(formData: FormData) {
  const clientId = String(formData.get("clientId") || "");
  if (!clientId) return { ok: false as const, error: "Missing client" };

  const body = {
    date: String(formData.get("date") || ""),
    annotation_type: String(formData.get("annotation_type") || "manual_note"),
    growth_action: String(formData.get("growth_action") || "").trim() || null,
    description: String(formData.get("description") || "").trim(),
    page_url: String(formData.get("page_url") || "").trim() || null,
    success_metric: String(formData.get("success_metric") || "").trim() || null,
    completed_at: String(formData.get("completed_at") || "").trim() || null,
    measurement_start_date: String(formData.get("measurement_start_date") || "").trim() || null,
    measurement_end_date: String(formData.get("measurement_end_date") || "").trim() || null,
    notes: String(formData.get("notes") || "").trim() || null,
    result: String(formData.get("result") || "not_yet_measured"),
  };

  if (!body.date || !body.description) {
    return { ok: false as const, error: "Date and description are required." };
  }

  try {
    await apiFetch("/annotations", { method: "POST", clientId, body });
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "Failed to create annotation",
    };
  }

  revalidatePath("/annotations");
  return { ok: true as const };
}

export async function importAnnotationsAction(formData: FormData) {
  const clientId = String(formData.get("clientId") || "");
  const csvText = String(formData.get("csv_text") || "");
  if (!clientId) return { ok: false as const, error: "Missing client" };
  if (!csvText.trim()) return { ok: false as const, error: "Paste or upload CSV content." };

  try {
    const result = await apiFetch<{ created: number; errors: Array<{ row: number; error: string }> }>(
      "/annotations/import",
      {
        method: "POST",
        clientId,
        body: { csv_text: csvText },
      },
    );
    revalidatePath("/annotations");
    return { ok: true as const, ...result };
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "Import failed",
    };
  }
}

export async function remeasureAnnotationsAction(formData: FormData) {
  const clientId = String(formData.get("clientId") || "");
  if (!clientId) return;
  await apiFetch("/annotations/remeasure", { method: "POST", clientId, body: {} });
  revalidatePath("/annotations");
}

export async function saveBaselineAction(formData: FormData) {
  const clientId = String(formData.get("clientId") || "");
  if (!clientId) return { ok: false as const, error: "Missing client" };

  const sessionsRaw = String(formData.get("baseline_monthly_sessions") || "").trim();
  const leadsRaw = String(formData.get("baseline_monthly_leads") || "").trim();
  const rateRaw = String(formData.get("baseline_lead_rate_pct") || "").trim();
  const goalRaw = String(formData.get("monthly_lead_goal") || "").trim();
  const asOf = String(formData.get("baseline_as_of") || "").trim() || null;

  const sessions = sessionsRaw === "" ? null : Number(sessionsRaw);
  const leads = leadsRaw === "" ? null : Number(leadsRaw);
  let rate = rateRaw === "" ? null : Number(rateRaw);
  const goal = goalRaw === "" ? null : Number(goalRaw);

  if ([sessions, leads, rate, goal].some((value) => value != null && Number.isNaN(value))) {
    return { ok: false as const, error: "Baseline values must be numbers." };
  }
  if (rate == null && sessions && leads && sessions > 0) {
    rate = (leads / sessions) * 100;
  }

  try {
    await apiFetch(`/clients/${clientId}`, {
      method: "PATCH",
      clientId,
      body: {
        baseline_as_of: asOf,
        baseline_monthly_sessions: sessions,
        baseline_monthly_leads: leads,
        baseline_lead_rate_pct: rate,
        baseline_source: String(formData.get("baseline_source") || "manual"),
        baseline_notes: String(formData.get("baseline_notes") || "").trim() || null,
        monthly_lead_goal: goal,
      },
    });
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "Failed to save baseline",
    };
  }

  revalidatePath("/clients", "layout");
  revalidatePath("/dashboard");
  return { ok: true as const };
}
