import { NextResponse } from "next/server";

import { getProxyAuthHeaders } from "@/lib/proxy-auth";
import { renderCsvSections, type CsvSection } from "@/lib/csv";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type SearchRow = {
  keyword: string;
  group_name: string | null;
  volume: number | null;
  current_position: number | null;
  previous_position: number | null;
  ranking_change: number | null;
  earned_serp_features: string[];
  ranking_url: string | null;
  checked_at: string | null;
};

type AiRow = {
  prompt: string;
  engine: string;
  group_name: string | null;
  search_volume: number | null;
  brand_mentioned: boolean | null;
  brand_cited: boolean | null;
  mention_position: number | null;
  url_position: number | null;
  citation_url: string | null;
  checked_at: string | null;
};

function bool(value: boolean | null): string {
  if (value === null) return "";
  return value ? "Yes" : "No";
}

async function fetchRows<T>(path: string, clientId: string, headers: Record<string, string>) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { ...headers, "X-OrganicIQ-Client-Id": clientId },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${path} failed with ${res.status}`);
  return (await res.json()) as T[];
}

export async function GET(request: Request) {
  const authHeaders = await getProxyAuthHeaders();
  if (!authHeaders) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const params = new URL(request.url).searchParams;
  const clientId = params.get("clientId");
  if (!clientId) {
    return NextResponse.json({ detail: "clientId required" }, { status: 400 });
  }
  // Which tab the user is on; "all" ships both.
  const tab = params.get("tab") === "ai" ? "ai" : params.get("tab") === "all" ? "all" : "search";

  const sections: CsvSection[] = [];

  try {
    if (tab === "search" || tab === "all") {
      const rows = await fetchRows<SearchRow>("/watch-list/search", clientId, authHeaders);
      sections.push({
        title: "Search keywords",
        headers: [
          "Keyword",
          "Group",
          "Volume",
          "Position",
          "Previous",
          "Change",
          "SERP features",
          "Ranking URL",
          "Checked at",
        ],
        rows: rows.map((row) => [
          row.keyword,
          row.group_name ?? "",
          row.volume ?? "",
          row.current_position ?? "",
          row.previous_position ?? "",
          row.ranking_change ?? "",
          (row.earned_serp_features ?? []).join(" | "),
          row.ranking_url ?? "",
          row.checked_at ?? "",
        ]),
      });
    }

    if (tab === "ai" || tab === "all") {
      const rows = await fetchRows<AiRow>("/watch-list/ai", clientId, authHeaders);
      sections.push({
        title: "AI prompts",
        headers: [
          "Prompt",
          "Engine",
          "Group",
          "Search volume",
          "Mentioned",
          "Cited",
          "Mention position",
          "Citation position",
          "Citation URL",
          "Checked at",
        ],
        rows: rows.map((row) => [
          row.prompt,
          row.engine,
          row.group_name ?? "",
          row.search_volume ?? "",
          bool(row.brand_mentioned),
          bool(row.brand_cited),
          row.mention_position ?? "",
          row.url_position ?? "",
          row.citation_url ?? "",
          row.checked_at ?? "",
        ]),
      });
    }
  } catch (e) {
    return NextResponse.json(
      { detail: e instanceof Error ? e.message : "Failed to load watch list" },
      { status: 502 },
    );
  }

  const csv = renderCsvSections(sections);
  const stamp = new Date().toISOString().slice(0, 10);

  return new NextResponse(csv, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="organiciq-watch-list-${tab}-${stamp}.csv"`,
      "Cache-Control": "no-store",
    },
  });
}
