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

  const serviceChoice = String(formData.get("service_reporting") ?? "");
  if (formData.has("service_reporting") && !["", "none", "organiciq", "ad_accelerator", "both"].includes(serviceChoice)) return { ok: false as const, error: "Choose a valid agency service." };
  const services = serviceChoice ? { organiciq: ["organiciq", "both"].includes(serviceChoice), ad_accelerator: ["ad_accelerator", "both"].includes(serviceChoice) } : null;
  const monthlyRaw = String(formData.get("monthly_lead_goal") || "").trim();
  const sheetRaw = String(formData.get("account_sheet_url") || "").trim();
  const startRaw = String(formData.get("start_date") || "").trim();
  const isEnterprise = String(formData.get("is_enterprise") || "") === "1";
  // Staff cannot change the plan or its ceilings (the API refuses), and the
  // form does not send them. Leaving them out of the body leaves them alone.
  const planLocked = String(formData.get("plan_locked") || "") === "1";

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
  // A per-client cost ceiling, not an allowance: it bounds what one untracked-prompt
  // lookup can spend. The API clamps it again before any credits are spent.
  const aiPromptLimit = parseOptionalInt("ai_search_prompt_limit");
  const crawlPageLimit = parseOptionalInt("crawl_page_limit");
  const sitemapUrl = String(formData.get("sitemap_url") || "").trim() || null;
  const pathPrefix = String(formData.get("path_prefix") || "").trim() || null;
  // One name per line. The API lowercases, dedupes and drops anything too
  // short to be a name.
  const brandAliases = String(formData.get("brand_aliases") || "")
    .split(/[\n;]/)
    .map((name) => name.trim())
    .filter(Boolean);

  // One domain per line, at most three: each is a 100-credit SE Ranking read a
  // month. The API cleans them to bare domains and refuses a fourth.
  const competitorDomains = String(formData.get("competitor_domains") || "")
    .split(/[\n;,]/)
    .map((name) => name.trim())
    .filter(Boolean);

  // One input per checkpoint, named lead_goal_<month>. A blank box means "use
  // the projection", so it is left out rather than sent as zero.
  const leadGoalOverrides: Record<string, number> = {};
  for (const [key, value] of formData.entries()) {
    const match = /^lead_goal_(\d+)$/.exec(key);
    if (!match) continue;
    const goal = Number(String(value).trim());
    if (Number.isFinite(goal) && goal > 0) leadGoalOverrides[match[1]] = Math.round(goal);
  }

  if (
    [customKeyword, customPrompt, customContent, customRefresh, customGrowth].some((value) =>
      Number.isNaN(value),
    )
  ) {
    return { ok: false as const, error: "Custom allowances must be numbers." };
  }
  if (Number.isNaN(aiPromptLimit)) {
    return { ok: false as const, error: "AI prompt limit must be a number." };
  }
  if (aiPromptLimit != null && (aiPromptLimit < 1 || aiPromptLimit > 50)) {
    return { ok: false as const, error: "AI prompt limit must be between 1 and 50." };
  }
  if (Number.isNaN(crawlPageLimit)) {
    return { ok: false as const, error: "Crawl page limit must be a number." };
  }
  if (crawlPageLimit != null && (crawlPageLimit < 1 || crawlPageLimit > 5000)) {
    return { ok: false as const, error: "Crawl page limit must be between 1 and 5,000." };
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

  // The market dropdown keeps whatever was already stored as a selectable
  // option, under a sentinel. Choosing it means "leave it alone", so the
  // field is omitted rather than saved as the sentinel.
  const marketRaw = String(formData.get("primary_market") || "").trim();
  const market = marketRaw === "__other" ? undefined : marketRaw || null;

  const body = {
    ...(formData.has("service_reporting") ? { service_reporting: services } : {}),
    client_name: String(formData.get("client_name") || "").trim(),
    domain: String(formData.get("domain") || "").trim(),
    ...(planLocked ? {} : { tier_id: String(formData.get("tier_id") || "").trim() }),
    start_date: startRaw || null,
    ...(market === undefined ? {} : { primary_market: market }),
    timezone: String(formData.get("timezone") || "").trim() || "America/New_York",
    monthly_lead_goal: monthlyRaw === "" ? null : Number(monthlyRaw),
    account_sheet_url: sheetRaw || null,
    teamwork_tasklist_id:
      String(formData.get("teamwork_tasklist_id") || "").trim() || null,
    status: String(formData.get("status") || "active"),
    ...(planLocked
      ? {}
      : {
          custom_tracked_keyword_limit: isEnterprise ? customKeyword : null,
          custom_tracked_prompt_limit: isEnterprise ? (customPrompt ?? customKeyword) : null,
          custom_content_allowance: isEnterprise ? customContent : null,
          custom_update_allowance: isEnterprise ? customRefresh : null,
          custom_growth_action_allowance: isEnterprise ? customGrowth : null,
          custom_watchlist_cadence: isEnterprise ? customCadence || "monthly" : null,
          ai_search_prompt_limit: aiPromptLimit,
          crawl_page_limit: crawlPageLimit,
        }),
    sitemap_url: sitemapUrl,
    path_prefix: pathPrefix,
    brand_aliases: brandAliases,
    competitor_domains: competitorDomains,
    lead_goal_overrides: leadGoalOverrides,
  };

  if (!body.client_name || !body.domain || (!planLocked && !("tier_id" in body && body.tier_id))) {
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

  revalidatePath("/clients", "layout");
  revalidatePath("/dashboard");
  revalidatePath("/decision-engine");
  return { ok: true as const };
}
