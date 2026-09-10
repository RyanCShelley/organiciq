/**
 * Pure date-range and compare-mode helpers.
 *
 * Deliberately NOT a client module: server components (the dashboard page)
 * import `parseCompareMode` / `comparisonLabelFor` from here.
 */

export type RangeKey =
  | "today"
  | "7d"
  | "14d"
  | "30d"
  | "60d"
  | "90d"
  | "6m"
  | "12m"
  | "custom";

export type CompareMode = "none" | "prev" | "baseline";

export const RANGE_OPTIONS: { key: RangeKey; label: string; days?: number }[] = [
  { key: "today", label: "Today", days: 1 },
  { key: "7d", label: "Last 7 days", days: 7 },
  { key: "14d", label: "Last 14 days", days: 14 },
  { key: "30d", label: "Last 30 days", days: 30 },
  { key: "60d", label: "Last 60 days", days: 60 },
  { key: "90d", label: "Last 90 days", days: 90 },
  { key: "6m", label: "Last 6 months", days: 182 },
  { key: "12m", label: "Last 12 months", days: 365 },
  { key: "custom", label: "Custom" },
];

/** Timeframe dropdown in the app top bar. */
export const TOPBAR_RANGE_OPTIONS: { key: RangeKey; label: string; days?: number }[] = [
  { key: "7d", label: "Last 7 days", days: 7 },
  { key: "14d", label: "Last 14 days", days: 14 },
  { key: "30d", label: "Last 30 days", days: 30 },
  { key: "60d", label: "Last 60 days", days: 60 },
  { key: "90d", label: "Last 90 days", days: 90 },
  { key: "custom", label: "Custom range" },
];

/** Compare dropdown. `none` suppresses every delta pill and comparison string. */
export const COMPARE_OPTIONS: { key: CompareMode; label: string }[] = [
  { key: "none", label: "Compare: none" },
  { key: "prev", label: "Compare: previous period" },
  { key: "baseline", label: "Compare: baseline" },
];

/** Trailing copy for a metric card's comparison string. */
export function comparisonLabelFor(compare: CompareMode): string {
  return compare === "baseline" ? "vs baseline" : "vs previous period";
}

export function parseCompareMode(raw: string | string[] | undefined): CompareMode {
  return raw === "baseline" || raw === "none" ? raw : "prev";
}

export function isoDaysAgo(days: number): { from: string; to: string } {
  const to = new Date();
  const from = new Date();
  from.setUTCDate(to.getUTCDate() - (days - 1));
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

export function detectRangeKey(from: string, to: string, explicit?: string | null): RangeKey {
  if (explicit === "custom") return "custom";
  if (explicit && RANGE_OPTIONS.some((o) => o.key === explicit)) {
    return explicit as RangeKey;
  }

  for (const option of RANGE_OPTIONS) {
    if (!option.days) continue;
    const expected = isoDaysAgo(option.days);
    if (expected.from === from && expected.to === to) return option.key;
  }
  return "custom";
}

export function formatDateLabel(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
