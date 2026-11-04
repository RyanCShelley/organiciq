export type ActionResult = { ok: true } | { ok: false; error: string };

/** The agency services a client buys. There is no "none": a client we serve has at least one. */
export const SERVICES = [
  { value: "organiciq", label: "OrganicIQ" },
  { value: "ad_accelerator", label: "Ad Accelerator" },
  { value: "both", label: "OrganicIQ + Ad Accelerator" },
] as const;

export type ServiceValue = (typeof SERVICES)[number]["value"];

export function serviceFromConfig(
  config: { organiciq: boolean; ad_accelerator: boolean } | null | undefined,
): ServiceValue | "" {
  if (!config) return "";
  if (config.organiciq && config.ad_accelerator) return "both";
  if (config.organiciq) return "organiciq";
  if (config.ad_accelerator) return "ad_accelerator";
  return "";
}

export function configFromService(value: ServiceValue) {
  return { organiciq: value !== "ad_accelerator", ad_accelerator: value !== "organiciq" };
}

/** How a client earns, which decides what the dashboard and baseline measure. */
export const BUSINESS_MODELS = [
  { value: "lead_gen", label: "Lead generation" },
  { value: "ecommerce", label: "Ecommerce" },
  { value: "both", label: "Both" },
] as const;

export const STATUSES = [
  { value: "onboarding", label: "Onboarding" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "archived", label: "Archived" },
] as const;

/** The SE Ranking indexes the domain pull can read. A country, not a city. */
export const SEARCH_MARKETS = ["United States", "United Kingdom", "Canada", "Australia"] as const;

/** One entry per line, blanks dropped. */
export function lines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}
