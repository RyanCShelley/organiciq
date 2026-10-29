/** Allow only the fields owned by the visible settings form. Missing fields
 * must never clear another section's saved configuration. API role checks
 * remain authoritative; this list is a boundary against accidental overwrites. */
export const SETTINGS_FIELDS = {
  general: ["service_reporting", "client_name", "domain", "tier_id", "start_date", "status", "account_sheet_url", "custom_tracked_keyword_limit", "custom_tracked_prompt_limit", "custom_content_allowance", "custom_update_allowance", "custom_growth_action_allowance", "custom_watchlist_cadence"],
  connections: ["teamwork_tasklist_id"],
  goals: ["monthly_lead_goal", "lead_goal_overrides"],
  competitors: ["competitor_domains"],
  advanced: ["primary_market", "timezone", "path_prefix", "brand_aliases", "sitemap_url", "crawl_page_limit"],
} as const;
export type SettingsSection = keyof typeof SETTINGS_FIELDS;
export function isSettingsSection(value: string): value is SettingsSection {
  return Object.hasOwn(SETTINGS_FIELDS, value);
}
export function settingsPatch(body: Record<string, unknown>, section: SettingsSection) {
  const fields: readonly string[] = SETTINGS_FIELDS[section];
  return Object.fromEntries(Object.entries(body).filter(([key]) => fields.includes(key)));
}
