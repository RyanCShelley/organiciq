import Link from "next/link";
import { redirect } from "next/navigation";

import { Download } from "lucide-react";

import { DataTable } from "@/components/analytics/DataTable";
import { AiPresenceSummary } from "@/components/analytics/AiPresenceSummary";
import { PositionDistribution } from "@/components/analytics/PositionDistribution";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch } from "@/lib/api";
import { accountToolHref } from "@/lib/account-routes";
import { requireAccountClient } from "@/lib/account-routes.server";
import { resolveDateRange } from "@/lib/context";
import { withNavContext } from "@/lib/navigation";

type SearchRow = {
  keyword_id: string;
  keyword: string;
  group_name: string | null;
  site_engine_id: string;
  volume: number | null;
  current_position: number | null;
  previous_position: number | null;
  ranking_change: number | null;
  earned_serp_features: string[];
  ranking_url: string | null;
  checked_at: string | null;
};

type AiRow = {
  prompt_id: string;
  prompt: string;
  engine: string;
  group_name: string | null;
  search_volume: number | null;
  search_intent: string[];
  url_position: number | null;
  mention_position: number | null;
  url_position_change: number | null;
  mention_position_change: number | null;
  brand_mentioned: boolean | null;
  brand_cited: boolean | null;
  citation_url: string | null;
  ai_visibility: number | null;
  ai_sov: number | null;
  checked_at: string | null;
};

function formatNum(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function formatBool(value: boolean | null): string {
  if (value === null) return "—";
  return value ? "Yes" : "No";
}

/**
 * checked_at arrives as a full ISO timestamp. Rendered raw it is ~32 characters
 * in a narrow column, which is what made the dates look cramped. Show the date,
 * keep the exact time in the tooltip.
 */
function CheckedAt({ value }: { value: string | null }) {
  if (!value) return <span className="text-[var(--text-tertiary)]">—</span>;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return <span className="whitespace-nowrap">{value}</span>;
  }
  return (
    <span className="whitespace-nowrap text-[var(--text-secondary)]" title={value}>
      {parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
    </span>
  );
}

function formatSerpFeatures(features: string[]): string {
  return features.length > 0 ? features.join(", ") : "—";
}

type WatchTab = "search" | "ai";

function resolveTab(raw: string | string[] | undefined): WatchTab {
  if (raw === "ai") return "ai";
  return "search";
}

export default async function WatchListPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clientSlug } = await params;
  const query = await searchParams;
  const client = await requireAccountClient(clientSlug, "watch-list");
  const clientId = client.id;

  // Legacy Content Opp lived under Watch List — send bookmarks to the standalone tool.
  if (query.tab === "content-opp" || query.tab === "content") {
    const qs = new URLSearchParams();
    if (typeof query.from === "string") qs.set("from", query.from);
    if (typeof query.to === "string") qs.set("to", query.to);
    if (typeof query.range === "string") qs.set("range", query.range);
    const suffix = qs.toString();
    redirect(
      suffix
        ? `${accountToolHref(client.slug, "content-opp")}?${suffix}`
        : accountToolHref(client.slug, "content-opp"),
    );
  }

  const tab = resolveTab(query.tab);
  const { from, to } = await resolveDateRange(query);

  let searchRows: SearchRow[] = [];
  let aiRows: AiRow[] = [];
  let error: string | null = null;

  if (tab === "search") {
    try {
      searchRows = await apiFetch<SearchRow[]>("/watch-list/search", {
        clientId,
      });
    } catch (e) {
      error =
        e instanceof Error ? e.message : "Failed to load Search Watch List";
    }
  } else {
    try {
      aiRows = await apiFetch<AiRow[]>("/watch-list/ai", { clientId });
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load AI Watch List";
    }
  }

  const tabs: { id: WatchTab; label: string }[] = [
    { id: "search", label: "Search" },
    { id: "ai", label: "AI" },
  ];
  const watchHref = accountToolHref(client.slug, "watch-list");

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="segmented" role="tablist" aria-label="Watch List tabs">
          {tabs.map((item) => {
            const href = withNavContext(watchHref, clientId, from, to, {
              tab: item.id === "search" ? undefined : item.id,
            });
            const active = tab === item.id;
            return (
              <Link
                key={item.id}
                href={href}
                className={
                  active
                    ? "segmented-item segmented-item-active"
                    : "segmented-item"
                }
              >
                {item.label}
              </Link>
            );
          })}
        </div>

        <a
          className="btn btn-secondary gap-2"
          href={`/api/export/watch-list?clientId=${encodeURIComponent(clientId)}&tab=${tab}`}
          download
        >
          <Download className="h-3.5 w-3.5" aria-hidden />
          Export {tab === "ai" ? "prompts" : "keywords"}
        </a>
      </div>

      {error ? (
        <Alert variant="danger" className="mt-4">
          {error}
        </Alert>
      ) : null}

      {tab === "search" && searchRows.length > 0 ? (
        <PositionDistribution
          className="mt-4"
          positions={searchRows.map((row) => row.current_position)}
        />
      ) : null}

      {tab === "ai" && aiRows.length > 0 ? (
        <AiPresenceSummary className="mt-4" rows={aiRows} />
      ) : null}

      {tab === "search" ? (
        <section className="mt-4 workspace-section">
          <SectionHeader
            title="Search keywords"
            description="Tracked keyword positions from SE Ranking."
            actions={
              <span className="text-xs text-[var(--text-tertiary)]">
                {searchRows.length} keyword{searchRows.length === 1 ? "" : "s"}
              </span>
            }
          />
          <div className="workspace-panel">
            {!error && searchRows.length === 0 ? (
              <Alert variant="info">
                No Search Watch List rows yet. Map an SE Ranking project in
                Client settings → Integrations and run Sync Search 14 days.
              </Alert>
            ) : (
              <DataTable
                columns={[
                  {
                    key: "keyword",
                    header: "Keyword",
                    render: (row) => (
                      <span className="block max-w-[22rem] truncate" title={row.keyword}>
                        {row.keyword}
                      </span>
                    ),
                  },
                  {
                    key: "group",
                    header: "Group",
                    render: (row) => row.group_name ?? "—",
                  },
                  {
                    key: "volume",
                    header: "Volume",
                    align: "right",
                    render: (row) => formatNum(row.volume),
                  },
                  {
                    key: "position",
                    header: "Position",
                    align: "right",
                    render: (row) => formatNum(row.current_position),
                  },
                  {
                    key: "change",
                    header: "Change",
                    align: "right",
                    render: (row) => formatNum(row.ranking_change),
                  },
                  {
                    key: "serp",
                    header: "SERP Features",
                    render: (row) =>
                      formatSerpFeatures(row.earned_serp_features),
                  },
                  {
                    key: "checked",
                    header: "Checked",
                    render: (row) => <CheckedAt value={row.checked_at} />,
                  },
                ]}
                rows={searchRows}
                getRowKey={(row) => `${row.site_engine_id}-${row.keyword_id}`}
                emptyMessage="No search keywords."
              />
            )}
          </div>
        </section>
      ) : null}

      {tab === "ai" ? (
        <section className="mt-4 workspace-section">
          <SectionHeader
            title="AI prompts"
            description="Tracked AI visibility prompts from SE Ranking."
            actions={
              <span className="text-xs text-[var(--text-tertiary)]">
                {aiRows.length} prompt{aiRows.length === 1 ? "" : "s"}
              </span>
            }
          />
          <div className="workspace-panel">
            {!error && aiRows.length === 0 ? (
              <Alert variant="info">
                No AI Watch List rows yet. Map an SE Ranking project in Client
                settings → Integrations and run Sync AI 14 days.
              </Alert>
            ) : (
              <DataTable
                columns={[
                  {
                    key: "prompt",
                    header: "Prompt",
                    render: (row) => (
                      // Unconstrained free text was squeezing every other
                      // column on this tab.
                      <span className="block max-w-[26rem] truncate" title={row.prompt}>
                        {row.prompt}
                      </span>
                    ),
                  },
                  {
                    key: "engine",
                    header: "Engine",
                    render: (row) => row.engine,
                  },
                  {
                    key: "group",
                    header: "Group",
                    render: (row) => row.group_name ?? "—",
                  },
                  {
                    key: "mentioned",
                    header: "Mentioned",
                    render: (row) => formatBool(row.brand_mentioned),
                  },
                  {
                    key: "cited",
                    header: "Cited",
                    render: (row) => formatBool(row.brand_cited),
                  },
                  {
                    key: "mention_pos",
                    header: "Mention Pos",
                    align: "right",
                    render: (row) => formatNum(row.mention_position),
                  },
                  {
                    key: "citation_pos",
                    header: "Citation Pos",
                    align: "right",
                    render: (row) => formatNum(row.url_position),
                  },
                  {
                    key: "checked",
                    header: "Checked",
                    render: (row) => <CheckedAt value={row.checked_at} />,
                  },
                ]}
                rows={aiRows}
                getRowKey={(row) => `${row.engine}-${row.prompt_id}`}
                emptyMessage="No AI prompts."
              />
            )}
          </div>
        </section>
      ) : null}
    </section>
  );
}
