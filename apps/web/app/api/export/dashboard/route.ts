import { NextResponse } from "next/server";

import { getProxyAuthHeaders } from "@/lib/proxy-auth";
import { renderCsvSections, type CsvSection } from "@/lib/csv";
import {
  normalizeDashboardResponse,
  type DashboardPeriodMetric,
  type DashboardResponse,
} from "@/lib/dashboard";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function metricRow(label: string, metric: DashboardPeriodMetric): unknown[] {
  return [label, metric.current ?? "", metric.previous ?? "", metric.change_pct ?? ""];
}

const METRIC_HEADERS = ["Metric", "Current", "Previous", "Change %"];

function buildSections(data: DashboardResponse): CsvSection[] {
  const { conversions, visibility, traffic, baseline } = data;

  return [
    {
      title: "Period",
      headers: ["From", "To", "Previous from", "Previous to"],
      rows: [
        [data.period.from, data.period.to, data.period.previous_from, data.period.previous_to],
      ],
    },
    {
      title: "Conversions",
      headers: METRIC_HEADERS,
      rows: [
        metricRow("Leads", conversions.leads),
        metricRow("Lead rate %", conversions.lead_rate),
        ["Monthly lead goal", conversions.monthly_lead_goal ?? "", "", ""],
        ["Period lead goal", conversions.period_lead_goal ?? "", "", ""],
        ["Goal period days", conversions.goal_period_days ?? "", "", ""],
        ["Goal progress %", conversions.goal_progress_pct ?? "", "", ""],
      ],
    },
    {
      title: "Leads by channel",
      headers: ["Channel", "Leads"],
      rows: conversions.leads_by_channel.map((row) => [row.label, row.leads]),
    },
    {
      title: "Visibility — search",
      headers: METRIC_HEADERS,
      rows: [
        metricRow("Search visibility", visibility.search.search_visibility),
        metricRow("Search SOV %", visibility.search.search_sov),
        metricRow("GSC impressions", visibility.search.gsc_impressions),
        metricRow("Average position", visibility.search.average_position),
      ],
    },
    {
      title: "Visibility — AI",
      headers: METRIC_HEADERS,
      rows: [
        metricRow("Answers with mention %", visibility.ai.mention_presence),
        metricRow("Answers with link %", visibility.ai.link_presence),
        metricRow("Mention in top 3 %", visibility.ai.mention_top3_presence),
        metricRow("Link in top 3 %", visibility.ai.link_top3_presence),
        ["Tracked prompts", visibility.ai.prompt_count ?? "", "", ""],
      ],
    },
    {
      title: "Traffic",
      headers: METRIC_HEADERS,
      rows: [
        metricRow("GSC clicks", traffic.gsc_clicks),
        metricRow("GSC CTR %", traffic.gsc_ctr),
        metricRow("GA4 sessions", traffic.ga4_sessions),
        metricRow("GA4 views", traffic.ga4_views),
      ],
    },
    {
      title: "Traffic by channel",
      headers: ["Channel", "Sessions", "Views", "Conversions", "Bounce rate %"],
      rows: traffic.by_channel.map((row) => [
        row.label,
        row.sessions,
        row.views,
        row.conversions,
        row.bounce_rate ?? "",
      ]),
    },
    {
      title: "Top pages",
      headers: ["Page", "GSC impressions", "GSC clicks", "GA4 sessions", "GA4 views"],
      rows: traffic.top_pages.map((row) => [
        row.page,
        row.gsc_impressions,
        row.gsc_clicks,
        row.ga4_sessions,
        row.ga4_views,
      ]),
    },
    {
      title: "Baseline",
      headers: ["Field", "Value"],
      rows: [
        ["Configured", baseline.configured ? "yes" : "no"],
        ["As of", baseline.as_of ?? ""],
        ["Source", baseline.source ?? ""],
        ["Tier", baseline.tier_name ?? ""],
        ["Monthly sessions", baseline.monthly_sessions ?? ""],
        ["Monthly leads", baseline.monthly_leads ?? ""],
        ["Lead rate %", baseline.lead_rate ?? ""],
      ],
    },
    {
      title: "Baseline vs current",
      headers: METRIC_HEADERS,
      rows: [
        metricRow("Monthly sessions", baseline.vs_current.sessions),
        metricRow("Monthly leads", baseline.vs_current.leads),
        metricRow("Lead rate %", baseline.vs_current.lead_rate),
      ],
    },
  ];
}

export async function GET(request: Request) {
  const authHeaders = await getProxyAuthHeaders();
  if (!authHeaders) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const params = new URL(request.url).searchParams;
  const clientId = params.get("clientId");
  const from = params.get("from");
  const to = params.get("to");

  if (!clientId) {
    return NextResponse.json({ detail: "clientId required" }, { status: 400 });
  }
  if (!from || !to || !ISO_DATE.test(from) || !ISO_DATE.test(to)) {
    return NextResponse.json({ detail: "from and to must be YYYY-MM-DD" }, { status: 400 });
  }

  const res = await fetch(
    `${API_URL}/dashboard?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    {
      headers: { ...authHeaders, "X-OrganicIQ-Client-Id": clientId },
      cache: "no-store",
    },
  );

  if (!res.ok) {
    return NextResponse.json(
      { detail: (await res.text()) || res.statusText },
      { status: res.status },
    );
  }

  const data = normalizeDashboardResponse(await res.json());
  const csv = renderCsvSections(buildSections(data));

  return new NextResponse(csv, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="organiciq-dashboard-${from}-to-${to}.csv"`,
      "Cache-Control": "no-store",
    },
  });
}
