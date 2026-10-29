export type EventCandidate = {
  event_name: string;
  event_count: number;
  pages: number;
  last_seen: string | null;
  automatic: boolean;
  suggested: boolean;
  defined: boolean;
  conversion_name: string | null;
  conversion_type: string | null;
  is_primary: boolean | null;
  active: boolean | null;
};

export type ConversionDefinition = {
  event_name: string;
  conversion_name: string;
  conversion_type: string;
  is_primary: boolean;
  active: boolean;
};

export type ConversionPage = {
  normalized_url: string;
  label: string;
  stage: string | null;
  is_primary: boolean;
};

export const CONVERSION_TYPES = [
  { value: "lead", label: "Lead" },
  { value: "ecommerce", label: "Ecommerce" },
  { value: "engagement", label: "Engagement" },
] as const;

export type Ga4Page = {
  url: string;
  path: string;
  total: number;
  events: Record<string, number>;
  declared: boolean;
};

export type Ga4PagesResult = { ok: true; pages: Ga4Page[] } | { ok: false; error: string };

/** "/pages/contact-us" -> "Contact us"; the home page -> "Home". */
export function labelFromPath(path: string): string {
  const last = path.split("?")[0].split("/").filter(Boolean).pop();
  if (!last) return "Home";
  const text = decodeURIComponent(last).replace(/[-_]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}
