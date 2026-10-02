"use client";

import { useMemo, useState } from "react";

import { DataTable, type SortState } from "@/components/analytics/DataTable";
import { Input } from "@/components/ui/Input";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { formatNum, type SearchOpportunity } from "@/lib/decision-engine";

const PAGE_SIZE = 25;

/**
 * Page type says what the page is for; opportunity type says what work it
 * needs. Different palettes so the two columns stay distinguishable at a
 * glance rather than reading as one band of colour.
 */
const PAGE_TYPE_STYLES: Record<string, string> = {
  conversion: "bg-[var(--success-soft)] text-[var(--success)]",
  commercial: "bg-[rgb(0_169_157_/_12%)] text-[var(--brand-teal-hover)]",
  consideration: "bg-[rgb(170_228_55_/_28%)] text-[#4d6b0a]",
  informational: "bg-[var(--surface-muted)] text-[var(--text-secondary)]",
  utility: "bg-[#F1F2F3] text-[var(--text-tertiary)]",
};

const OPPORTUNITY_TYPE_STYLES: Record<string, string> = {
  "CTR gap": "bg-[var(--warning-soft)] text-[var(--warning)]",
  "Near win": "bg-[rgb(170_228_55_/_28%)] text-[#4d6b0a]",
  "Striking distance": "bg-[var(--accent-soft)] text-[var(--brand-teal-hover)]",
};

/**
 * What the three labels mean, taken from `_classify_opportunity` rather than
 * paraphrased — a key that drifts from the rule is worse than none.
 *
 * The order is the engine's own precedence, which is also roughly cheapest
 * work first, so sorting by type puts the quickest wins on top.
 */
const OPPORTUNITY_TYPES: { value: string; meaning: string }[] = [
  {
    value: "CTR gap",
    meaning: "Ranking is fine but clicks are under half what the position should earn — the listing, not the page",
  },
  { value: "Near win", meaning: "Averaging position 5 or better: a small push moves it into the top results" },
  { value: "Striking distance", meaning: "Ranking below position 5 with no particular click problem — the broad middle" },
];

const TYPE_RANK: Record<string, number> = Object.fromEntries(
  OPPORTUNITY_TYPES.map((row, index) => [row.value, index]),
);

/** Counts open biggest-first; rankings and labels open at the useful end. */
const COLUMN_SORT_INITIAL: Record<string, "asc" | "desc"> = {
  opportunity_type: "asc",
  page_type: "asc",
  position: "asc",
};

const CHIP = "inline-flex rounded-full px-2 py-0.5 text-[11px] font-bold tracking-[0.02em]";

function Chip({ value, styles }: { value: string; styles: Record<string, string> }) {
  return (
    <span className={`${CHIP} ${styles[value] ?? "bg-[#F1F2F3] text-[var(--text-secondary)]"}`}>
      {value}
    </span>
  );
}

export function SearchOpportunitiesTable({
  items,
  title = "Search Opportunities",
  description = "Striking-distance rankings for strategist review.",
}: {
  items: SearchOpportunity[];
  title?: string;
  description?: string;
}) {
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  // Impressions descending is how the list already arrived; making it the
  // starting sort means clicking a header changes the order rather than
  // revealing that it was never what you thought.
  const [sort, setSort] = useState<SortState>({ key: "impressions", dir: "desc" });

  function toggleSort(key: string) {
    setSort((current) => {
      if (current.key === key) {
        return { key, dir: current.dir === "desc" ? "asc" : "desc" };
      }
      const column = COLUMN_SORT_INITIAL[key] ?? "desc";
      return { key, dir: column };
    });
    setVisibleCount(PAGE_SIZE);
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((row) => {
      const url = (row.page_url ?? "").toLowerCase();
      const q = (row.query ?? "").toLowerCase();
      return url.includes(needle) || q.includes(needle);
    });
  }, [items, query]);

  const visible = filtered.slice(0, visibleCount);
  const remaining = Math.max(0, filtered.length - visible.length);

  if (items.length === 0) return null;

  return (
    <section id="search-opportunities" className="workspace-section scroll-mt-24">
      <SectionHeader
        title={title}
        description={description}
        actions={
          <span className="text-xs text-[var(--text-tertiary)]">
            Showing {visible.length} of {filtered.length}
            {filtered.length !== items.length ? ` (filtered from ${items.length})` : ""}
          </span>
        }
      />

      <div className="mb-3 max-w-md">
        <Input
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setVisibleCount(PAGE_SIZE);
          }}
          placeholder="Search by page URL or query…"
          aria-label="Search content opportunities"
        />
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">No opportunities match that search.</p>
      ) : (
        <>
          <DataTable
            columns={[
              {
                key: "url",
                header: "URL",
                render: (row) => (
                  <div className="max-w-xs break-all">
                    {row.page_url ?? "—"}
                    {row.query ? (
                      <div className="mt-0.5 text-xs text-[var(--text-tertiary)]">
                        Query: {row.query}
                      </div>
                    ) : null}
                  </div>
                ),
              },
              {
                key: "impressions",
                sortValue: (row) => row.impressions ?? null,
                header: "Impressions",
                align: "right",
                render: (row) => formatNum(row.impressions, 0),
              },
              {
                key: "clicks",
                sortValue: (row) => row.clicks ?? null,
                header: "Clicks",
                align: "right",
                render: (row) => formatNum(row.clicks, 0),
              },
              {
                key: "ctr",
                sortValue: (row) => row.ctr_percent ?? null,
                header: "CTR",
                align: "right",
                render: (row) => (row.ctr_percent != null ? `${row.ctr_percent}%` : "—"),
              },
              {
                key: "position",
                sortValue: (row) => row.average_position ?? null,
                sortInitial: "asc",
                header: "Avg Position",
                align: "right",
                render: (row) => formatNum(row.average_position),
              },
              {
                key: "page_type",
                header: "Page Type",
                sortValue: (row) => row.page_type ?? null,
                render: (row) =>
                  row.page_type ? (
                    <Chip value={row.page_type} styles={PAGE_TYPE_STYLES} />
                  ) : (
                    <span className="text-[var(--text-tertiary)]">—</span>
                  ),
              },
              {
                key: "tracked_keywords",
                sortValue: (row) => row.tracked_keywords ?? null,
                header: "Tracked KWs",
                align: "right",
                render: (row) =>
                  row.tracked_keywords > 0 ? (
                    <span
                      className="font-semibold text-[var(--brand-teal-hover)]"
                      title="Tracked SE Ranking keywords already ranking on this page"
                    >
                      {row.tracked_keywords}
                    </span>
                  ) : (
                    <span className="text-[var(--text-tertiary)]">—</span>
                  ),
              },
              {
                key: "opportunity_type",
                header: "Opportunity Type",
                sortValue: (row) => TYPE_RANK[row.opportunity_type] ?? 99,
                sortInitial: "asc",
                render: (row) => (
                  <Chip value={row.opportunity_type} styles={OPPORTUNITY_TYPE_STYLES} />
                ),
              },
            ]}
            rows={visible}
            getRowKey={(row) => row.rule_key}
            sort={sort}
            onSortChange={toggleSort}
          />

          <dl className="mt-4 grid gap-x-5 gap-y-2 text-xs sm:grid-cols-3">
            {OPPORTUNITY_TYPES.map((row) => (
              <div key={row.value} className="flex flex-col gap-1">
                <dt>
                  <Chip value={row.value} styles={OPPORTUNITY_TYPE_STYLES} />
                </dt>
                <dd className="text-[var(--text-secondary)]">{row.meaning}</dd>
              </div>
            ))}
          </dl>

          {remaining > 0 ? (
            <div className="mt-3">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}
              >
                Show {Math.min(PAGE_SIZE, remaining)} more
              </button>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
