"use client";

import { useMemo, useState } from "react";

import { DataTable } from "@/components/analytics/DataTable";
import { Input } from "@/components/ui/Input";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { formatNum, type SearchOpportunity } from "@/lib/decision-engine";

const PAGE_SIZE = 25;

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

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((row) => {
      const url = (row.page_url ?? "").toLowerCase();
      const topic = (row.topic ?? "").toLowerCase();
      const q = (row.query ?? "").toLowerCase();
      return url.includes(needle) || topic.includes(needle) || q.includes(needle);
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
          placeholder="Search by page URL, topic, or query…"
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
                key: "topic",
                header: "Topic",
                render: (row) => (
                  <span className="text-[var(--text-secondary)]">{row.topic ?? "—"}</span>
                ),
              },
              {
                key: "impressions",
                header: "Impressions",
                align: "right",
                render: (row) => formatNum(row.impressions, 0),
              },
              {
                key: "clicks",
                header: "Clicks",
                align: "right",
                render: (row) => formatNum(row.clicks, 0),
              },
              {
                key: "ctr",
                header: "CTR",
                align: "right",
                render: (row) => (row.ctr_percent != null ? `${row.ctr_percent}%` : "—"),
              },
              {
                key: "position",
                header: "Avg Position",
                align: "right",
                render: (row) => formatNum(row.average_position),
              },
              {
                key: "page_type",
                header: "Page Type",
                render: (row) => (
                  <span className="text-[var(--text-secondary)]">{row.page_type ?? "—"}</span>
                ),
              },
              {
                key: "opportunity_type",
                header: "Opportunity Type",
                render: (row) => row.opportunity_type,
              },
            ]}
            rows={visible}
            getRowKey={(row) => row.rule_key}
          />

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
