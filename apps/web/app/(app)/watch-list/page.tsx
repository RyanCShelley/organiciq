import Link from "next/link";
import { redirect } from "next/navigation";

import { DataTable } from "@/components/analytics/DataTable";
import { Alert } from "@/components/ui/Alert";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch } from "@/lib/api";
import { resolveClientId, resolveDateRange } from "@/lib/context";
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

function formatSerpFeatures(features: string[]): string {
  return features.length > 0 ? features.join(", ") : "—";
}

type WatchTab = "search" | "ai";

function resolveTab(raw: string | string[] | undefined): WatchTab {
  if (raw === "ai") return "ai";
  return "search";
}

export default async function WatchListPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  // Legacy Content Opp lived under Watch List — send bookmarks to the standalone tool.
  if (params.tab === "content-opp" || params.tab === "content") {
    const qs = new URLSearchParams();
    if (typeof params.clientId === "string") qs.set("clientId", params.clientId);
    if (typeof params.from === "string") qs.set("from", params.from);
    if (typeof params.to === "string") qs.set("to", params.to);
    if (typeof params.range === "string") qs.set("range", params.range);
    const suffix = qs.toString();
    redirect(suffix ? `/content-opp?${suffix}` : "/content-opp");
  }

  const tab = resolveTab(params.tab);
  const clientId = await resolveClientId(params);
  const { from, to } = await resolveDateRange(params);

  let searchRows: SearchRow[] = [];
  let aiRows: AiRow[] = [];
  let error: string | null = null;

  if (!clientId) {
    error = "Select a client to view the Watch List.";
  } else if (tab === "search") {
    try {
      searchRows = await apiFetch<SearchRow[]>("/watch-list/search", { clientId });
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load Search Watch List";
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

  return (
    <section>
      <PageHeader
        title="Watch List"
        description="Search keywords and AI prompts from SE Ranking."
      />

      <div className="mt-4 flex flex-wrap gap-2 text-sm">
        {tabs.map((item) => {
          const href = clientId
            ? withNavContext("/watch-list", clientId, from, to, {
                tab: item.id === "search" ? undefined : item.id,
              })
            : `/watch-list?tab=${item.id}`;
          const active = tab === item.id;
          return (
            <Link
              key={item.id}
              href={href}
              className={active ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm"}
            >
              {item.label}
            </Link>
          );
        })}
      </div>

      {error ? <Alert variant="danger" className="mt-4">{error}</Alert> : null}

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
                No Search Watch List rows yet. Map an SE Ranking project in Client settings →
                Integrations and run Sync Search 14 days.
              </Alert>
            ) : (
              <DataTable
                columns={[
                  { key: "keyword", header: "Keyword", render: (row) => row.keyword },
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
                    render: (row) => formatSerpFeatures(row.earned_serp_features),
                  },
                  {
                    key: "checked",
                    header: "Checked",
                    render: (row) => row.checked_at ?? "—",
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
                No AI Watch List rows yet. Map an SE Ranking project in Client settings →
                Integrations and run Sync AI 14 days.
              </Alert>
            ) : (
              <DataTable
                columns={[
                  { key: "prompt", header: "Prompt", render: (row) => row.prompt },
                  { key: "engine", header: "Engine", render: (row) => row.engine },
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
                    render: (row) => row.checked_at ?? "—",
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
