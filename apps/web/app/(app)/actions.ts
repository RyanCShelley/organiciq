"use server";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/api";
import { signOut } from "@/lib/auth";

export async function signOutAction() {
  await signOut({ redirectTo: "/login" });
}

export async function updateClientSettingsAction(formData: FormData) {
  const clientId = String(formData.get("clientId") || "");
  if (!clientId) return { ok: false as const, error: "Missing client" };

  const monthlyRaw = String(formData.get("monthly_lead_goal") || "").trim();
  const sheetRaw = String(formData.get("account_sheet_url") || "").trim();
  const startRaw = String(formData.get("start_date") || "").trim();
  const isEnterprise = String(formData.get("is_enterprise") || "") === "1";

  const baselineAsOf = String(formData.get("baseline_as_of") || "").trim() || null;
  const baselineSessionsRaw = String(formData.get("baseline_monthly_sessions") || "").trim();
  const baselineLeadsRaw = String(formData.get("baseline_monthly_leads") || "").trim();
  const baselineRateRaw = String(formData.get("baseline_lead_rate_pct") || "").trim();
  const baselineSessions =
    baselineSessionsRaw === "" ? null : Number(baselineSessionsRaw);
  const baselineLeads = baselineLeadsRaw === "" ? null : Number(baselineLeadsRaw);
  let baselineRate = baselineRateRaw === "" ? null : Number(baselineRateRaw);
  if (
    baselineRate == null &&
    baselineSessions != null &&
    baselineLeads != null &&
    baselineSessions > 0 &&
    !Number.isNaN(baselineSessions) &&
    !Number.isNaN(baselineLeads)
  ) {
    baselineRate = (baselineLeads / baselineSessions) * 100;
  }

  const parseOptionalInt = (key: string): number | null => {
    const raw = String(formData.get(key) || "").trim();
    if (raw === "") return null;
    const value = Number(raw);
    return Number.isNaN(value) ? Number.NaN : value;
  };

  const customKeyword = parseOptionalInt("custom_tracked_keyword_limit");
  const customPrompt = parseOptionalInt("custom_tracked_prompt_limit");
  const customContent = parseOptionalInt("custom_content_allowance");
  const customRefresh = parseOptionalInt("custom_update_allowance");
  const customGrowth = parseOptionalInt("custom_growth_action_allowance");
  const customCadence = String(formData.get("custom_watchlist_cadence") || "").trim() || null;

  if (
    [customKeyword, customPrompt, customContent, customRefresh, customGrowth].some((value) =>
      Number.isNaN(value),
    )
  ) {
    return { ok: false as const, error: "Custom allowances must be numbers." };
  }
  if (
    [baselineSessions, baselineLeads, baselineRate].some(
      (value) => value != null && Number.isNaN(value),
    )
  ) {
    return { ok: false as const, error: "Baseline values must be numbers." };
  }

  if (isEnterprise) {
    if (
      customKeyword == null ||
      customContent == null ||
      customRefresh == null ||
      customGrowth == null
    ) {
      return {
        ok: false as const,
        error: "Enterprise requires custom watchlist, content, refresh, and Growth Action amounts.",
      };
    }
  }

  const body = {
    client_name: String(formData.get("client_name") || "").trim(),
    domain: String(formData.get("domain") || "").trim(),
    tier_id: String(formData.get("tier_id") || "").trim(),
    start_date: startRaw || null,
    primary_market: String(formData.get("primary_market") || "").trim() || null,
    timezone: String(formData.get("timezone") || "").trim() || "America/New_York",
    monthly_lead_goal: monthlyRaw === "" ? null : Number(monthlyRaw),
    account_sheet_url: sheetRaw || null,
    baseline_as_of: baselineAsOf,
    baseline_monthly_sessions: baselineSessions,
    baseline_monthly_leads: baselineLeads,
    baseline_lead_rate_pct: baselineRate,
    baseline_source: String(formData.get("baseline_source") || "").trim() || "manual",
    baseline_notes: String(formData.get("baseline_notes") || "").trim() || null,
    status: String(formData.get("status") || "active"),
    custom_tracked_keyword_limit: isEnterprise ? customKeyword : null,
    custom_tracked_prompt_limit: isEnterprise ? (customPrompt ?? customKeyword) : null,
    custom_content_allowance: isEnterprise ? customContent : null,
    custom_update_allowance: isEnterprise ? customRefresh : null,
    custom_growth_action_allowance: isEnterprise ? customGrowth : null,
    custom_watchlist_cadence: isEnterprise ? customCadence || "monthly" : null,
  };

  if (!body.client_name || !body.domain || !body.tier_id) {
    return { ok: false as const, error: "Name, domain, and tier are required." };
  }
  if (body.monthly_lead_goal != null && Number.isNaN(body.monthly_lead_goal)) {
    return { ok: false as const, error: "Monthly lead goal must be a number." };
  }

  try {
    await apiFetch(`/clients/${clientId}`, {
      method: "PATCH",
      clientId,
      body,
    });
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "Failed to save client settings",
    };
  }

  revalidatePath(`/clients/${clientId}`);
  revalidatePath("/dashboard");
  revalidatePath("/decision-engine");
  return { ok: true as const };
}

export async function updateDecisionStatusAction(formData: FormData) {
  const clientId = String(formData.get("clientId") || "");
  const decisionId = String(formData.get("decisionId") || "");
  const ruleKey = String(formData.get("ruleKey") || "");
  const status = String(formData.get("status") || "");
  const dismissalReason = String(formData.get("dismissal_reason") || "").trim() || null;
  const from = String(formData.get("from") || "");
  const to = String(formData.get("to") || "");

  if (!clientId || !status || (!decisionId && !ruleKey)) {
    return { ok: false as const, error: "Missing decision update fields" };
  }
  if (status === "dismissed" && !dismissalReason) {
    return { ok: false as const, error: "Dismissal reason is required." };
  }

  try {
    let id = decisionId;

    // Persist recommended or additional findings for this period before status change.
    if (!id && ruleKey && from && to) {
      const ensured = await apiFetch<{ id: string; rule_key: string }>("/decisions/ensure", {
        method: "POST",
        clientId,
        body: { from, to, rule_key: ruleKey },
      });
      id = ensured.id;
    }

    if (!id) {
      return {
        ok: false as const,
        error: "Could not store this finding as a decision for the selected period.",
      };
    }

    await apiFetch(`/decisions/${id}`, {
      method: "PATCH",
      clientId,
      body: {
        status,
        dismissal_reason: status === "dismissed" ? dismissalReason : null,
      },
    });
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "Failed to update decision",
    };
  }

  revalidatePath("/decision-engine");
  return { ok: true as const };
}

export async function createTeamworkTaskStubAction(formData: FormData) {
  const clientId = String(formData.get("clientId") || "");
  const ruleKey = String(formData.get("ruleKey") || "");
  const from = String(formData.get("from") || "");
  const to = String(formData.get("to") || "");
  const decisionId = String(formData.get("decisionId") || "");

  if (!clientId || !from || !to) {
    return { ok: false as const, error: "Missing client or date range" };
  }

  try {
    let id = decisionId;
    if (!id && ruleKey) {
      const ensured = await apiFetch<{ id: string; rule_key: string }>("/decisions/ensure", {
        method: "POST",
        clientId,
        body: { from, to, rule_key: ruleKey },
      });
      id = ensured.id;
    }
    if (!id) {
      return { ok: false as const, error: "Could not resolve a stored decision for this finding." };
    }

    await apiFetch(`/decisions/${id}`, {
      method: "PATCH",
      clientId,
      body: { status: "task_created" },
    });
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "Failed to mark task created",
    };
  }

  revalidatePath("/decision-engine");
  return { ok: true as const };
}
