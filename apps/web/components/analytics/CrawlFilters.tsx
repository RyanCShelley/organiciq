import Link from "next/link";

/**
 * Crawl filters, as links rather than a form.
 *
 * Server-rendered like the rest of the page, so the filter state lives in the
 * URL: refreshing keeps it and a filtered view can be sent to someone.
 */

export type FilterGroup = {
  param: string;
  label: string;
  options: { value: string; label: string }[];
  /** The value that means "no filter" and so needs no chip. */
  defaultValue?: string;
};

export const CRAWL_FILTERS: FilterGroup[] = [
  {
    param: "status",
    label: "Status",
    options: [
      { value: "", label: "Any" },
      { value: "ok", label: "2xx" },
      { value: "redirect", label: "3xx" },
      { value: "error", label: "4xx / 5xx" },
    ],
  },
  {
    param: "indexable",
    label: "Indexable",
    options: [
      { value: "", label: "Any" },
      { value: "yes", label: "Yes" },
      { value: "no", label: "No" },
    ],
  },
  {
    param: "links",
    label: "Editorial links",
    options: [
      { value: "", label: "Any" },
      { value: "orphan", label: "None" },
      { value: "linked", label: "Has some" },
    ],
  },
  {
    param: "words",
    label: "Words",
    options: [
      { value: "", label: "Any" },
      { value: "thin", label: "Under 500" },
      { value: "substantial", label: "500+" },
    ],
  },
  {
    param: "schema",
    label: "Schema",
    options: [
      { value: "", label: "Any" },
      { value: "yes", label: "Present" },
      { value: "none", label: "None" },
    ],
  },
  {
    param: "sitemap",
    label: "Sitemap",
    options: [
      { value: "", label: "Any" },
      { value: "in", label: "In" },
      { value: "missing", label: "Missing" },
    ],
  },
  {
    param: "pagination",
    label: "Pagination",
    defaultValue: "hide",
    options: [
      { value: "hide", label: "Hidden" },
      { value: "show", label: "Included" },
      { value: "only", label: "Only these" },
    ],
  },
];

function hrefWith(
  base: string,
  active: Record<string, string>,
  param: string,
  value: string,
): string {
  const next = { ...active, [param]: value };
  const qs = new URLSearchParams();
  for (const [key, val] of Object.entries(next)) {
    if (val) qs.set(key, val);
  }
  const suffix = qs.toString();
  return suffix ? `${base}?${suffix}` : base;
}

export function CrawlFilters({
  base,
  active,
  matched,
  total,
}: {
  base: string;
  active: Record<string, string>;
  matched: number;
  total: number;
}) {
  const applied = CRAWL_FILTERS.filter((group) => {
    const value = active[group.param] ?? "";
    return value !== (group.defaultValue ?? "");
  });

  return (
    <div className="mt-4 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-muted)] p-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        {CRAWL_FILTERS.map((group) => {
          const current = active[group.param] ?? group.defaultValue ?? "";
          return (
            <div key={group.param} className="flex items-center gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]">
                {group.label}
              </span>
              <div className="segmented">
                {group.options.map((option) => (
                  <Link
                    key={option.value || "any"}
                    href={hrefWith(base, active, group.param, option.value)}
                    className={
                      current === option.value
                        ? "segmented-item segmented-item-active"
                        : "segmented-item"
                    }
                  >
                    {option.label}
                  </Link>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-3 text-[12px] text-[var(--text-secondary)]">
        <span>
          <strong className="text-[var(--text-primary)]">{matched.toLocaleString()}</strong> of{" "}
          {total.toLocaleString()} pages
        </span>
        {applied.length > 0 ? (
          <Link href={base} className="font-semibold text-[var(--brand-teal-hover)] hover:underline">
            Clear filters
          </Link>
        ) : null}
      </div>
    </div>
  );
}
