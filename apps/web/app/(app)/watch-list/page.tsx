import { apiFetch } from "@/lib/api";
import { resolveClientId } from "@/lib/context";

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

export default async function WatchListPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const tab = typeof params.tab === "string" ? params.tab : "search";
  const clientId = await resolveClientId(params);

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
  } else if (tab === "ai") {
    try {
      aiRows = await apiFetch<AiRow[]>("/watch-list/ai", { clientId });
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load AI Watch List";
    }
  }

  return (
    <section>
      <h1 className="text-2xl font-semibold">Watch List</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Search keywords and AI prompts from SE Ranking.
      </p>

      <div className="mt-4 flex gap-2 text-sm">
        <a
          href={clientId ? `/watch-list?tab=search&clientId=${clientId}` : "/watch-list?tab=search"}
          className={`rounded-lg px-3 py-1.5 ${
            tab === "search" ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"
          }`}
        >
          Search
        </a>
        <a
          href={clientId ? `/watch-list?tab=ai&clientId=${clientId}` : "/watch-list?tab=ai"}
          className={`rounded-lg px-3 py-1.5 ${
            tab === "ai" ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"
          }`}
        >
          AI
        </a>
      </div>

      {error ? (
        <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
          {error}
        </p>
      ) : null}

      {tab === "search" ? (
        <>
          {!error && searchRows.length === 0 ? (
            <p className="mt-6 text-sm text-[var(--muted)]">
              No Search Watch List rows yet. Map an SE Ranking project in Admin → Integrations and run
              Sync Search 14 days.
            </p>
          ) : null}

          {searchRows.length > 0 ? (
            <div className="mt-6 overflow-x-auto rounded-xl border border-[var(--border)]">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-white/5 text-[var(--muted)]">
                  <tr>
                    <th className="px-4 py-3 font-medium">Keyword</th>
                    <th className="px-4 py-3 font-medium">Group</th>
                    <th className="px-4 py-3 font-medium">Volume</th>
                    <th className="px-4 py-3 font-medium">Position</th>
                    <th className="px-4 py-3 font-medium">Change</th>
                    <th className="px-4 py-3 font-medium">SERP Features</th>
                    <th className="px-4 py-3 font-medium">Checked</th>
                  </tr>
                </thead>
                <tbody>
                  {searchRows.map((r) => (
                    <tr key={`${r.site_engine_id}-${r.keyword_id}`} className="border-t border-[var(--border)]">
                      <td className="px-4 py-3">{r.keyword}</td>
                      <td className="px-4 py-3 text-[var(--muted)]">{r.group_name ?? "—"}</td>
                      <td className="px-4 py-3 text-[var(--muted)]">{formatNum(r.volume)}</td>
                      <td className="px-4 py-3">{formatNum(r.current_position)}</td>
                      <td className="px-4 py-3 text-[var(--muted)]">{formatNum(r.ranking_change)}</td>
                      <td className="px-4 py-3 text-[var(--muted)]">
                        {formatSerpFeatures(r.earned_serp_features)}
                      </td>
                      <td className="px-4 py-3 text-[var(--muted)]">{r.checked_at ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      ) : (
        <>
          {!error && aiRows.length === 0 ? (
            <p className="mt-6 text-sm text-[var(--muted)]">
              No AI Watch List rows yet. Map an SE Ranking project in Admin → Integrations and run Sync AI
              14 days.
            </p>
          ) : null}

          {aiRows.length > 0 ? (
            <div className="mt-6 overflow-x-auto rounded-xl border border-[var(--border)]">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-white/5 text-[var(--muted)]">
                  <tr>
                    <th className="px-4 py-3 font-medium">Prompt</th>
                    <th className="px-4 py-3 font-medium">Engine</th>
                    <th className="px-4 py-3 font-medium">Group</th>
                    <th className="px-4 py-3 font-medium">Mentioned</th>
                    <th className="px-4 py-3 font-medium">Cited</th>
                    <th className="px-4 py-3 font-medium">Mention Pos</th>
                    <th className="px-4 py-3 font-medium">Citation Pos</th>
                    <th className="px-4 py-3 font-medium">Checked</th>
                  </tr>
                </thead>
                <tbody>
                  {aiRows.map((r) => (
                    <tr key={`${r.engine}-${r.prompt_id}`} className="border-t border-[var(--border)]">
                      <td className="px-4 py-3">{r.prompt}</td>
                      <td className="px-4 py-3 text-[var(--muted)]">{r.engine}</td>
                      <td className="px-4 py-3 text-[var(--muted)]">{r.group_name ?? "—"}</td>
                      <td className="px-4 py-3">{formatBool(r.brand_mentioned)}</td>
                      <td className="px-4 py-3">{formatBool(r.brand_cited)}</td>
                      <td className="px-4 py-3 text-[var(--muted)]">{formatNum(r.mention_position)}</td>
                      <td className="px-4 py-3 text-[var(--muted)]">{formatNum(r.url_position)}</td>
                      <td className="px-4 py-3 text-[var(--muted)]">{r.checked_at ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
