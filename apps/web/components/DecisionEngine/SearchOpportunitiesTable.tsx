import { DataTable } from "@/components/analytics/DataTable";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { formatNum, type SearchOpportunity } from "@/lib/decision-engine";

export function SearchOpportunitiesTable({
  items,
  title = "Search Opportunities",
  description = "Striking-distance rankings for strategist review.",
}: {
  items: SearchOpportunity[];
  title?: string;
  description?: string;
}) {
  if (items.length === 0) return null;

  return (
    <section id="search-opportunities" className="workspace-section scroll-mt-24">
      <SectionHeader
        title={title}
        description={description}
        actions={
          <span className="text-xs text-[var(--text-tertiary)]">{items.length} opportunities</span>
        }
      />

      <DataTable
        columns={[
          {
            key: "url",
            header: "URL",
            render: (row) => (
              <div className="max-w-xs break-all">
                {row.page_url ?? "—"}
                {row.query ? (
                  <div className="mt-0.5 text-xs text-[var(--text-tertiary)]">Query: {row.query}</div>
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
        rows={items}
        getRowKey={(row) => row.rule_key}
      />
    </section>
  );
}
