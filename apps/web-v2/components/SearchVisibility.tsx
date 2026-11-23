"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  addWatchlistKeywordAction,
  termDetailAction,
} from "@/app/(app)/[clientSlug]/search-visibility/actions";
import { VisibilityCheckDrawer } from "@/components/VisibilityCheckDrawer";
import type { Client } from "@/lib/api";
import { presets } from "@/lib/bi";
import type { Sv, SvDetail, SvTerm, SvWeek } from "@/lib/search-visibility";

type ViewMode = "overview" | "terms";
type ChartMetric = "clicks" | "pos";
type TermFilter = "all" | "p1" | "mv" | "dis" | "ns";

const shortDate = (iso: string | null | undefined) => {
  if (!iso) return "";
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

const fullRange = (from: string, to: string) => {
  const f = new Date(`${from}T00:00:00`);
  const t = new Date(`${to}T00:00:00`);
  const fStr = f.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const tStr = t.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  return `${fStr} – ${tStr}`;
};

const shortPath = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";

const posGap = (t: SvTerm): number | null => {
  if (t.google.position == null || t.bing.position == null) return null;
  return Math.abs(t.google.position - t.bing.position);
};

const isSourcesDiffer = (t: SvTerm) => {
  const g = posGap(t);
  return (g != null && g >= 5) || Boolean(t.disagree);
};

const bestMove = (t: SvTerm): number | null => {
  if (t.move != null) return t.move;
  return t.bing.move;
};

const isMoved = (t: SvTerm) => {
  const gm = t.move;
  const bm = t.bing.move;
  return (gm != null && Math.abs(gm) >= 0.5) || (bm != null && Math.abs(bm) >= 0.5);
};

function matrixCellStyle(pos: number | null): { bg: string; fg: string; text: string } {
  if (pos == null) return { bg: "#ffffff", fg: "#909a9f", text: "—" };
  const label = `#${pos.toFixed(1).replace(/\.0$/, "")}`;
  if (pos <= 3) return { bg: "#223540", fg: "#ffffff", text: label };
  if (pos <= 10) return { bg: "#c6f2ed", fg: "#00665f", text: label };
  if (pos <= 20) return { bg: "#eef0f1", fg: "#171a22", text: label };
  return { bg: "#f8f8f8", fg: "#4a5560", text: label };
}

function deltaDisplay(
  now: number | null | undefined,
  before: number | null | undefined,
  { lowerIsBetter = false, suffix = "" }: { lowerIsBetter?: boolean; suffix?: string } = {},
): { text: string; color: string } {
  if (now == null || before == null) return { text: "no earlier figure", color: "#7a838c" };
  const diff = +(now - before).toFixed(1);
  if (diff === 0) return { text: "flat", color: "#7a838c" };
  const improved = lowerIsBetter ? diff < 0 : diff > 0;
  const abs = Math.abs(diff).toLocaleString("en-US");
  return {
    text: `${improved ? "▲" : "▼"} ${abs}${suffix} vs before`,
    color: improved ? "#00857b" : "oklch(0.52 0.17 25)",
  };
}

function WeeklyOverviewChart({
  weeks,
  gSeries,
  bSeries,
  updates,
  annotations,
  metric,
  hasGsc,
  onMetricChange,
}: {
  weeks: string[];
  gSeries: SvWeek[];
  bSeries: SvWeek[];
  updates: Sv["updates"];
  annotations: Sv["annotations"];
  metric: ChartMetric;
  hasGsc: boolean;
  onMetricChange: (m: ChartMetric) => void;
}) {
  const W = 720;
  const H = 220;
  const PAD_L = 36;
  const PAD_R = 12;
  const PAD_T = 16;
  const PAD_B = 28;
  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;

  const gVals = gSeries.map((s) => (metric === "clicks" ? (hasGsc ? s.clicks : null) : s.position));
  const bVals = bSeries.map((s) => (metric === "clicks" ? s.clicks : s.position));
  const allNums = [...gVals, ...bVals].filter((v): v is number => v != null);

  const minV = metric === "pos" ? Math.max(1, Math.floor(Math.min(...(allNums.length ? allNums : [1])))) : 0;
  const maxV =
    metric === "pos"
      ? Math.max(minV + 5, Math.ceil(Math.max(...(allNums.length ? allNums : [20]))))
      : Math.max(10, Math.ceil(Math.max(...(allNums.length ? allNums : [10])) * 1.15));

  const xAt = (idx: number) =>
    weeks.length <= 1 ? PAD_L + plotW / 2 : PAD_L + (idx / (weeks.length - 1)) * plotW;

  const yAt = (val: number) => {
    const ratio = (val - minV) / Math.max(0.001, maxV - minV);
    return metric === "pos" ? PAD_T + ratio * plotH : PAD_T + (1 - ratio) * plotH;
  };

  const buildPath = (vals: (number | null)[]) => {
    let d = "";
    vals.forEach((v, i) => {
      if (v == null) return;
      const cmd = d === "" || vals[i - 1] == null ? "M" : "L";
      d += `${cmd}${xAt(i).toFixed(1)} ${yAt(v).toFixed(1)} `;
    });
    return d.trim();
  };

  const gPath = buildPath(gVals);
  const bPath = buildPath(bVals);

  const gridTicks = [0, 0.5, 1].map((t) => {
    const val = minV + t * (maxV - minV);
    const y = yAt(val);
    return {
      y: y.toFixed(1),
      ty: (y + 3).toFixed(1),
      label: metric === "pos" ? `#${Math.round(val)}` : Math.round(val).toLocaleString("en-US"),
    };
  });

  const labelStep = Math.max(1, Math.floor(weeks.length / 4));
  const xLabels = weeks
    .map((w, i) => ({ w, i }))
    .filter(({ i }) => i === 0 || i === weeks.length - 1 || i % labelStep === 0)
    .slice(0, 5);

  const firstTs = weeks.length ? new Date(`${weeks[0]}T00:00:00`).getTime() : 0;
  const lastTs = weeks.length ? new Date(`${weeks[weeks.length - 1]}T00:00:00`).getTime() : 1;
  const spanTs = Math.max(1, lastTs - firstTs);
  const xForDate = (iso: string) => {
    const ts = new Date(`${iso}T00:00:00`).getTime();
    const ratio = Math.max(0, Math.min(1, (ts - firstTs) / spanTs));
    return PAD_L + ratio * plotW;
  };

  const updateBands = updates
    .map((u) => {
      if (!weeks.length) return null;
      const x1 = xForDate(u.begin);
      const x2 = u.end ? xForDate(u.end) : x1 + 14;
      const w = Math.max(10, x2 - x1);
      return { id: u.id, title: u.title, x: x1, w, tx: Math.min(W - 90, x1 + 4) };
    })
    .filter((b): b is { id: string; title: string; x: number; w: number; tx: number } => b !== null);

  const visMarkers = annotations
    .filter((a) => weeks.length > 0 && a.date >= weeks[0])
    .map((a) => ({ id: a.id, x: xForDate(a.date), label: a.description }));

  return (
    <div className="flex flex-col gap-2.5 rounded-xl border border-[#ececec] bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">
          {metric === "clicks" ? "Weekly clicks" : "Weekly average position"}
        </div>
        <div className="flex gap-0.5 rounded-full bg-[#f1f3f4] p-[3px]">
          {(
            [
              { id: "clicks", label: "Clicks" },
              { id: "pos", label: "Avg position" },
            ] as const
          ).map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => onMetricChange(m.id)}
              className={`cursor-pointer whitespace-nowrap rounded-full px-3 py-1 text-[11px] font-semibold transition-colors ${
                metric === m.id ? "bg-[#223540] text-white" : "text-[#4a5560] hover:text-[#0a0c0f]"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="block overflow-visible">
        {updateBands.map((b) => (
          <g key={b.id}>
            <rect x={b.x} y={PAD_T - 4} width={b.w} height={plotH + 8} fill="oklch(0.95 0.03 60)" />
            <text x={b.tx} y={PAD_T + 8} fontSize="10" fontWeight="600" fill="oklch(0.45 0.08 55)">
              {b.title.slice(0, 22)}
            </text>
          </g>
        ))}

        {visMarkers.map((m) => (
          <g key={m.id}>
            <line
              x1={m.x}
              x2={m.x}
              y1={PAD_T}
              y2={PAD_T + plotH}
              stroke="#00a99d"
              strokeWidth="1.2"
              strokeDasharray="3 3"
            />
            <circle cx={m.x} cy={PAD_T + 4} r="3.5" fill="#00a99d" />
            <title>{m.label}</title>
          </g>
        ))}

        {gridTicks.map((g, idx) => (
          <g key={idx}>
            <line x1={PAD_L} x2={W - PAD_R} y1={g.y} y2={g.y} stroke="#eef0f1" />
            <text x={PAD_L - 8} y={g.ty} fontSize="10" textAnchor="end" fill="#909a9f">
              {g.label}
            </text>
          </g>
        ))}

        {bPath ? <path d={bPath} fill="none" stroke="#223540" strokeWidth="2" strokeDasharray="5 4" /> : null}
        {gPath ? <path d={gPath} fill="none" stroke="#00a99d" strokeWidth="2.5" strokeLinejoin="round" /> : null}

        {xLabels.map(({ w, i }) => (
          <text key={w} x={xAt(i)} y={H - 8} fontSize="10" textAnchor="middle" fill="#909a9f">
            {shortDate(w)}
          </text>
        ))}
      </svg>

      <div className="flex flex-wrap items-center gap-4 text-[11px] text-[#4a5560]">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-[2.5px] w-3.5 bg-[#00a99d]" /> Google
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-3.5 border-t-2 border-dashed border-[#223540]" /> Bing
        </span>
        {updateBands.length > 0 ? (
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 bg-[oklch(0.95_0.03_60)]" /> Google update rolling out
          </span>
        ) : null}
        {visMarkers.length > 0 ? (
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-[#00a99d]" /> Visibility check logged
          </span>
        ) : null}
        {metric === "pos" ? <span className="text-[#7a838c]">Higher on the chart is better.</span> : null}
      </div>
    </div>
  );
}

function TermWeeklyChart({ weeks, trend }: { weeks: string[]; trend: (number | null)[] }) {
  const W = 640;
  const H = 150;
  const PAD_L = 30;
  const PAD_R = 10;
  const PAD_T = 12;
  const PAD_B = 22;
  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;

  const valid = trend.filter((v): v is number => v != null);
  if (valid.length === 0) {
    return (
      <div className="rounded-xl border border-[#ececec] bg-white p-4">
        <div className="font-[var(--font-heading)] text-[15px] font-bold text-[#0a0c0f]">
          Google position by week
        </div>
        <p className="mt-2 text-xs text-[#7a838c]">
          Not enough Search Console impressions in this range to draw a weekly trend.
        </p>
      </div>
    );
  }

  const minV = Math.max(1, Math.floor(Math.min(...valid)));
  const maxV = Math.max(minV + 4, Math.ceil(Math.max(...valid)));
  const xAt = (i: number) =>
    trend.length <= 1 ? PAD_L + plotW / 2 : PAD_L + (i / (trend.length - 1)) * plotW;
  const yAt = (v: number) => PAD_T + ((v - minV) / Math.max(0.001, maxV - minV)) * plotH;

  let path = "";
  trend.forEach((v, i) => {
    if (v == null) return;
    const cmd = path === "" || trend[i - 1] == null ? "M" : "L";
    path += `${cmd}${xAt(i).toFixed(1)} ${yAt(v).toFixed(1)} `;
  });

  const ticks = [minV, Math.round((minV + maxV) / 2), maxV];

  return (
    <div className="flex flex-col gap-2.5 rounded-xl border border-[#ececec] bg-white p-4">
      <div className="font-[var(--font-heading)] text-[15px] font-bold text-[#0a0c0f]">
        Google position by week
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="block">
        {ticks.map((t, idx) => {
          const y = yAt(t);
          return (
            <g key={idx}>
              <line x1={PAD_L} x2={W - PAD_R} y1={y} y2={y} stroke="#eef0f1" />
              <text x={PAD_L - 6} y={y + 3} fontSize="10" textAnchor="end" fill="#909a9f">
                #{t}
              </text>
            </g>
          );
        })}
        {path ? <path d={path.trim()} fill="none" stroke="#00a99d" strokeWidth="2.5" strokeLinejoin="round" /> : null}
        {weeks.length > 1 ? (
          <>
            <text x={PAD_L} y={H - 4} fontSize="10" fill="#909a9f">
              {shortDate(weeks[0])}
            </text>
            <text x={W - PAD_R} y={H - 4} fontSize="10" textAnchor="end" fill="#909a9f">
              {shortDate(weeks[weeks.length - 1])}
            </text>
          </>
        ) : null}
      </svg>
      <div className="text-[11px] text-[#7a838c]">
        Higher on the chart is better. Weeks with fewer than 10 impressions aren&apos;t drawn.
      </div>
    </div>
  );
}

export function SearchVisibility({
  client,
  from,
  to,
  bucket,
  data,
  error,
}: {
  client: Client;
  from: string;
  to: string;
  bucket: string;
  data: Sv | null;
  error: string | null;
}) {
  const router = useRouter();
  const [view, setView] = useState<ViewMode>("overview");
  const [metric, setMetric] = useState<ChartMetric>("clicks");
  const [filter, setFilter] = useState<TermFilter>("all");
  const [topicFilter, setTopicFilter] = useState<string>(bucket || "");
  const [query, setQuery] = useState("");
  const [matrixShowAll, setMatrixShowAll] = useState(false);
  const [selectedTermKey, setSelectedTermKey] = useState<string>(data?.terms[0]?.key ?? "");
  const [addedHeroes, setAddedHeroes] = useState<Record<string, boolean>>({});
  const [addingHeroKey, setAddingHeroKey] = useState<string | null>(null);
  const [removedKeys, setRemovedKeys] = useState<Record<string, boolean>>({});
  const [checkDrawerOpen, setCheckDrawerOpen] = useState(false);
  const [checkLogged, setCheckLogged] = useState(false);
  const [detail, setDetail] = useState<SvDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);
  const [customFrom, setCustomFrom] = useState(from);
  const [customTo, setCustomTo] = useState(to);

  const periodPresets = useMemo(() => presets(), []);
  const activePreset = periodPresets.find((p) => p.from === from && p.to === to)?.key ?? "custom";

  const hasGsc = Boolean(data?.sources.google_through);

  const activeTerms = useMemo(
    () => (data?.terms ?? []).filter((t) => !removedKeys[t.key]),
    [data?.terms, removedKeys],
  );

  const topicFilteredTerms = useMemo(
    () => (topicFilter ? activeTerms.filter((t) => t.bucket_id === topicFilter || t.bucket === topicFilter) : activeTerms),
    [activeTerms, topicFilter],
  );

  const filteredTerms = useMemo(() => {
    const q = query.trim().toLowerCase();
    return topicFilteredTerms
      .filter((t) => {
        if (q && !t.term.toLowerCase().includes(q) && !t.bucket.toLowerCase().includes(q)) return false;
        if (filter === "p1") return t.google.position != null && t.google.position <= 10;
        if (filter === "mv") return isMoved(t);
        if (filter === "dis") return isSourcesDiffer(t);
        if (filter === "ns") return t.google.position == null && t.bing.position == null && t.ser.position == null;
        return true;
      })
      .sort((a, b) => (b.volume ?? -1) - (a.volume ?? -1));
  }, [topicFilteredTerms, query, filter]);

  const filterCounts = useMemo(
    () => ({
      all: topicFilteredTerms.length,
      p1: topicFilteredTerms.filter((t) => t.google.position != null && t.google.position <= 10).length,
      mv: topicFilteredTerms.filter(isMoved).length,
      dis: topicFilteredTerms.filter(isSourcesDiffer).length,
      ns: topicFilteredTerms.filter((t) => t.google.position == null && t.bing.position == null && t.ser.position == null).length,
    }),
    [topicFilteredTerms],
  );

  const selectedTerm =
    filteredTerms.find((t) => t.key === selectedTermKey) ?? filteredTerms[0] ?? activeTerms[0] ?? null;

  useEffect(() => {
    if (view !== "terms" || !selectedTerm) return;
    let alive = true;
    setDetailLoading(true);
    termDetailAction(client.id, selectedTerm.term, from, to).then((res) => {
      if (!alive) return;
      setDetail(res.ok ? res.detail : null);
      setDetailLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [view, selectedTerm?.term, client.id, from, to]);

  const navigateRange = (nextFrom: string, nextTo: string, nextBucket = topicFilter) => {
    const qs = new URLSearchParams({ from: nextFrom, to: nextTo });
    if (nextBucket) qs.set("bucket", nextBucket);
    router.push(`/${client.slug}/search-visibility?${qs.toString()}`);
  };

  const handleAddHero = async (queryText: string, key: string) => {
    setAddingHeroKey(key);
    const defaultBucketId = data?.buckets[0]?.id ?? null;
    const res = await addWatchlistKeywordAction(client.id, {
      keyword: queryText,
      bucket_id: defaultBucketId,
      bucket_name: defaultBucketId ? null : "General",
    });
    setAddingHeroKey(null);
    if (res.ok) {
      setAddedHeroes((prev) => ({ ...prev, [key]: true }));
    }
  };

  const openTerm = (termKey: string) => {
    setSelectedTermKey(termKey);
    setView("terms");
  };

  if (error) {
    return (
      <section className="max-w-4xl space-y-4">
        <h1 className="font-[var(--font-heading)] text-2xl font-bold">Search visibility</h1>
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      </section>
    );
  }

  if (!data) return null;

  const combinedClicksNow = (hasGsc ? data.now.clicks : 0) + (data.sources.has_bing ? data.bing_now.clicks : 0);
  const combinedClicksBefore = (hasGsc ? data.before.clicks : 0) + (data.sources.has_bing ? data.bing_before.clicks : 0);
  const clicksDelta =
    hasGsc || data.sources.has_bing ? deltaDisplay(combinedClicksNow, combinedClicksBefore) : { text: "no data", color: "#7a838c" };

  const showingDelta = hasGsc ? deltaDisplay(data.now.showing, data.before.showing) : { text: "no data", color: "#7a838c" };
  const p1Delta = hasGsc ? deltaDisplay(data.now.page_one, data.before.page_one) : { text: "no data", color: "#7a838c" };
  const posDelta = hasGsc
    ? deltaDisplay(data.now.position, data.before.position, { lowerIsBetter: true })
    : { text: "no data", color: "#7a838c" };

  const distTotal = Math.max(1, data.terms_total);
  const distRows = [
    { key: "top3", label: "Top 3", color: "#223540" },
    { key: "top10", label: "4–10", color: "#00a99d" },
    { key: "top20", label: "11–20", color: "#909a9f" },
    { key: "beyond", label: "21+", color: "#c5cdd2" },
    { key: "none", label: "Not showing", color: "#e3e6e8" },
  ].map((b) => {
    const n = data.distribution.now[b.key] ?? 0;
    const p = data.distribution.before[b.key] ?? 0;
    return {
      ...b,
      n,
      p,
      w: `${Math.round((n / distTotal) * 100)}%`,
      pw: `${Math.round((p / distTotal) * 100)}%`,
    };
  });

  const serShowing = activeTerms.filter((t) => t.ser.position != null).length;
  const serP1 = activeTerms.filter((t) => t.ser.position != null && t.ser.position <= 10).length;
  const serPosList = activeTerms.map((t) => t.ser.position).filter((v): v is number => v != null);
  const serAvg = serPosList.length ? +(serPosList.reduce((a, b) => a + b, 0) / serPosList.length).toFixed(1) : null;

  const matrixTerms = [...activeTerms].sort((a, b) => (b.volume ?? -1) - (a.volume ?? -1));
  const shownMatrix = matrixShowAll ? matrixTerms : matrixTerms.slice(0, 8);

  const topicStats = data.buckets
    .map((b) => {
      const list = activeTerms.filter((t) => t.bucket_id === b.id);
      const p1 = list.filter((t) => t.google.position != null && t.google.position <= 10).length;
      const posList = list.map((t) => t.google.position).filter((v): v is number => v != null);
      const avg = posList.length ? (posList.reduce((a, c) => a + c, 0) / posList.length).toFixed(1) : "—";
      const share = list.length ? (p1 / list.length) * 100 : 0;
      return { id: b.id, name: b.name, n: list.length, p1, avg, share };
    })
    .filter((t) => t.n > 0)
    .sort((a, b) => b.share - a.share);

  const mergedMoves = activeTerms
    .flatMap((t) => {
      const out: {
        key: string;
        term: string;
        src: "Google" | "Bing";
        from: number;
        to: number;
        delta: number;
      }[] = [];
      if (t.move != null && Math.abs(t.move) >= 0.5 && t.google.position != null && t.google.position_before != null) {
        out.push({
          key: t.key,
          term: t.term,
          src: "Google",
          from: +t.google.position_before.toFixed(1),
          to: +t.google.position.toFixed(1),
          delta: +t.move.toFixed(1),
        });
      }
      if (t.bing.move != null && Math.abs(t.bing.move) >= 0.5 && t.bing.position != null && t.bing.position_before != null) {
        out.push({
          key: t.key,
          term: t.term,
          src: "Bing",
          from: +t.bing.position_before.toFixed(1),
          to: +t.bing.position.toFixed(1),
          delta: +t.bing.move.toFixed(1),
        });
      }
      return out;
    })
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
    .slice(0, 8);

  const activeTopicName = data.buckets.find((b) => b.id === topicFilter || b.name === topicFilter)?.name ?? topicFilter;

  return (
    <section className="-m-8 flex min-h-[calc(100vh-3.5rem)] flex-col bg-[#f6f7f7] lg:h-[calc(100vh-3.5rem)] lg:overflow-hidden">
      {/* Header */}
      <header className="flex flex-none flex-col gap-3 border-b border-[#e8e8e8] bg-white px-6 py-4 pb-3.5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="font-[var(--font-heading)] text-2xl font-bold text-[#0a0c0f]">Search visibility</h1>
              <div role="tablist" aria-label="Search visibility view" className="ml-1 flex gap-0.5 rounded-full bg-[#f1f3f4] p-[3px]">
                {(
                  [
                    { id: "overview", label: "Overview" },
                    { id: "terms", label: "Terms" },
                  ] as const
                ).map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    role="tab"
                    aria-selected={view === t.id}
                    onClick={() => setView(t.id)}
                    className={`cursor-pointer whitespace-nowrap rounded-full px-4 py-1 text-xs font-semibold transition-colors ${
                      view === t.id ? "bg-[#223540] text-white" : "text-[#4a5560] hover:text-[#0a0c0f]"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
            <p className="mt-0.5 text-[13px] text-[#4a5560]">
              Where your {data.terms_total} watchlist terms rank in Google and Bing, and what moved since the period before.
            </p>
          </div>

          <button
            type="button"
            onClick={() => setCheckDrawerOpen(true)}
            className={`flex-none cursor-pointer rounded-full border px-3.5 py-2 text-xs font-semibold transition-colors ${
              checkLogged
                ? "border-[#c6f2ed] bg-[#e6f7f5] text-[#00665f]"
                : "border-[#d3d7d9] bg-white text-[#223540] hover:border-[#e6f7f5] hover:bg-[#e6f7f5]"
            }`}
          >
            {checkLogged ? "Visibility check logged ✓" : "Log visibility check"}
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex gap-0.5 rounded-full border border-[#e3e6e8] p-0.5">
              {(
                [
                  { key: "28", label: "Last 28 days" },
                  { key: "90", label: "Last 3 months" },
                  { key: "365", label: "Last 12 months" },
                ] as const
              ).map((p) => {
                const match = periodPresets.find((x) => x.key === p.key);
                const isActive = activePreset === p.key && !customOpen;
                return (
                  <button
                    key={p.key}
                    type="button"
                    onClick={() => {
                      setCustomOpen(false);
                      if (match) navigateRange(match.from, match.to);
                    }}
                    className={`cursor-pointer whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
                      isActive ? "bg-[#223540] text-white" : "text-[#4a5560] hover:text-[#0a0c0f]"
                    }`}
                  >
                    {p.label}
                  </button>
                );
              })}
              <button
                type="button"
                onClick={() => setCustomOpen((v) => !v)}
                className={`cursor-pointer whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
                  activePreset === "custom" || customOpen ? "bg-[#223540] text-white" : "text-[#4a5560] hover:text-[#0a0c0f]"
                }`}
              >
                Custom
              </button>
            </div>

            {customOpen ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  setCustomOpen(false);
                  navigateRange(customFrom, customTo);
                }}
                className="flex items-center gap-1.5"
              >
                <input
                  type="date"
                  value={customFrom}
                  onChange={(e) => setCustomFrom(e.target.value)}
                  className="rounded-lg border border-[#e3e6e8] px-2 py-1 text-xs"
                />
                <span className="text-xs text-[#7a838c]">to</span>
                <input
                  type="date"
                  value={customTo}
                  onChange={(e) => setCustomTo(e.target.value)}
                  className="rounded-lg border border-[#e3e6e8] px-2 py-1 text-xs"
                />
                <button
                  type="submit"
                  className="cursor-pointer rounded-full bg-[#223540] px-3 py-1 text-xs font-semibold text-white"
                >
                  Apply
                </button>
              </form>
            ) : null}

            <select
              aria-label="Filter by topic"
              value={topicFilter}
              onChange={(e) => setTopicFilter(e.target.value)}
              className="rounded-full border border-[#e3e6e8] bg-white px-3 py-1 text-xs font-semibold text-[#223540]"
            >
              <option value="">All topics</option>
              {data.buckets.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>

            <span className="text-xs text-[#7a838c]">{fullRange(from, to)} vs. the period before</span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <span
              title={hasGsc ? `Google Search Console data through ${data.sources.google_through}` : "Search Console is not connected"}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                hasGsc
                  ? "bg-[#e6f7f5] text-[#00665f]"
                  : "bg-[oklch(0.965_0.025_25)] text-[oklch(0.48_0.17_25)]"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${hasGsc ? "bg-[#00a99d]" : "bg-[oklch(0.48_0.17_25)]"}`} />
              Search Console · {hasGsc ? shortDate(data.sources.google_through) : "not connected"}
            </span>

            <span
              title={data.sources.has_bing ? `Bing Webmaster weekly data through ${data.sources.bing_through}` : "No Bing Webmaster data"}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                data.sources.has_bing
                  ? "bg-[oklch(0.97_0.045_85)] text-[oklch(0.42_0.1_65)]"
                  : "bg-[#f1f3f4] text-[#7a838c]"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  data.sources.has_bing ? "bg-[oklch(0.68_0.16_65)]" : "bg-[#909a9f]"
                }`}
              />
              Bing · {data.sources.has_bing ? shortDate(data.sources.bing_through) : "no data"}
            </span>

            <span
              title={data.sources.ser_to ? `SE Ranking tracked ${data.sources.ser_tracked} terms through ${data.sources.ser_to}` : "No SE Ranking data"}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                data.sources.ser_to ? "bg-[#e6f7f5] text-[#00665f]" : "bg-[#f1f3f4] text-[#7a838c]"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${data.sources.ser_to ? "bg-[#00a99d]" : "bg-[#909a9f]"}`} />
              SE Ranking · {data.sources.ser_to ? shortDate(data.sources.ser_to) : "not tracked"}
            </span>
          </div>
        </div>
      </header>

      {/* Search Console Not Connected Banner */}
      {!hasGsc ? (
        <div className="mx-6 mt-4 flex flex-none flex-wrap items-center justify-between gap-4 rounded-xl border border-dashed border-[oklch(0.82_0.08_25)] bg-white px-4 py-3">
          <div>
            <div className="font-bold text-[oklch(0.48_0.17_25)]">Search Console isn&apos;t connected</div>
            <div className="text-[13px] text-[#4a5560]">
              Google numbers below stay empty until it is. Bing and SE Ranking still report.
            </div>
          </div>
          <Link
            href={`/${client.slug}/settings/connections`}
            className="flex-none rounded-full bg-[#223540] px-4 py-2 text-[13px] font-semibold text-white hover:opacity-90"
          >
            Connect Search Console
          </Link>
        </div>
      ) : null}

      {view === "overview" ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4 pb-8">
          <div className="space-y-4">
            {/* 1. Four KPI cards */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <div className="flex flex-col gap-2 rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">Terms showing</div>
                <div className="font-[var(--font-heading)] text-[30px] font-bold leading-none text-[#0a0c0f] tabular-nums">
                  {hasGsc ? data.now.showing : "—"}
                  <span className="ml-1.5 text-sm font-normal text-[#7a838c]">of {data.terms_total}</span>
                </div>
                <div className="text-xs font-semibold" style={{ color: showingDelta.color }}>
                  {showingDelta.text}
                </div>
                <div className="text-xs text-[#7a838c]">Watchlist terms with Google impressions</div>
              </div>

              <div className="flex flex-col gap-2 rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">On page one</div>
                <div className="font-[var(--font-heading)] text-[30px] font-bold leading-none text-[#0a0c0f] tabular-nums">
                  {hasGsc ? data.now.page_one : "—"}
                </div>
                <div className="text-xs font-semibold" style={{ color: p1Delta.color }}>
                  {p1Delta.text}
                </div>
                <div className="text-xs text-[#7a838c]">Ranking in positions 1–10 on Google</div>
              </div>

              <div className="flex flex-col gap-2 rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">Average position</div>
                <div className="font-[var(--font-heading)] text-[30px] font-bold leading-none text-[#0a0c0f] tabular-nums">
                  {hasGsc && data.now.position != null ? `#${data.now.position.toFixed(1)}` : "—"}
                </div>
                <div className="text-xs font-semibold" style={{ color: posDelta.color }}>
                  {posDelta.text}
                </div>
                <div className="text-xs text-[#7a838c]">Impression-weighted across showing terms</div>
              </div>

              <div className="flex flex-col gap-2 rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">Clicks</div>
                <div className="font-[var(--font-heading)] text-[30px] font-bold leading-none text-[#0a0c0f] tabular-nums">
                  {hasGsc || data.sources.has_bing ? combinedClicksNow.toLocaleString("en-US") : "—"}
                </div>
                <div className="text-xs font-semibold" style={{ color: clicksDelta.color }}>
                  {clicksDelta.text}
                </div>
                <div className="text-xs text-[#7a838c]">Google and Bing combined</div>
              </div>
            </div>

            {/* 2. Chart + Where the terms rank */}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.7fr_1fr]">
              <WeeklyOverviewChart
                weeks={data.weeks}
                gSeries={data.series}
                bSeries={data.bing_series}
                updates={data.updates}
                annotations={data.annotations}
                metric={metric}
                hasGsc={hasGsc}
                onMetricChange={setMetric}
              />

              <div className="flex flex-col gap-3 rounded-xl border border-[#ececec] bg-white p-4">
                <div>
                  <div className="font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">
                    Where the terms rank
                  </div>
                  <div className="text-xs text-[#7a838c]">Google position · this period vs. before</div>
                </div>
                <div className="space-y-3">
                  {distRows.map((d) => (
                    <div key={d.key} className="grid grid-cols-[84px_minmax(0,1fr)_56px] items-center gap-2.5 text-[13px]">
                      <span className="text-[#171a22]">{d.label}</span>
                      <div className="flex flex-col gap-1">
                        <span className="block h-2 overflow-hidden rounded bg-[#eef0f1]">
                          <span className="block h-full" style={{ width: d.w, background: d.color }} />
                        </span>
                        <span className="block h-[3px] overflow-hidden rounded bg-[#f4f5f5]">
                          <span className="block h-full bg-[#c5cdd2]" style={{ width: d.pw }} />
                        </span>
                      </div>
                      <span className="text-right text-[#4a5560] tabular-nums">
                        <strong className="text-[#0a0c0f]">{hasGsc ? d.n : "—"}</strong> / {hasGsc ? d.p : "—"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* 3. Performance by engine */}
            <div className="overflow-x-auto rounded-xl border border-[#ececec] bg-white p-4">
              <div className="mb-2 font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">
                Performance by engine
              </div>
              <div className="min-w-[680px]">
                <div className="grid grid-cols-[minmax(0,1.2fr)_repeat(4,minmax(0,1fr))_minmax(0,1.6fr)] gap-3 border-b border-[#eef0f1] py-1.5 text-[10px] font-bold uppercase tracking-[0.1em] text-[#909a9f]">
                  <span>Engine</span>
                  <span>Terms showing</span>
                  <span>Page one</span>
                  <span>Avg position</span>
                  <span>Clicks</span>
                  <span>Data</span>
                </div>

                {[
                  {
                    name: "Google",
                    dot: "#00a99d",
                    show: hasGsc ? String(data.now.showing) : "—",
                    showDelta: showingDelta,
                    p1: hasGsc ? String(data.now.page_one) : "—",
                    p1Delta,
                    avg: hasGsc && data.now.position != null ? `#${data.now.position.toFixed(1)}` : "—",
                    avgDelta: posDelta,
                    clk: hasGsc ? data.now.clicks.toLocaleString("en-US") : "—",
                    clkDelta: hasGsc ? deltaDisplay(data.now.clicks, data.before.clicks) : { text: "—", color: "#7a838c" },
                    note: hasGsc ? `Search Console · daily · through ${shortDate(data.sources.google_through)}` : "Search Console not connected",
                  },
                  {
                    name: "Bing",
                    dot: "#223540",
                    show: data.sources.has_bing ? String(data.bing_now.showing) : "—",
                    showDelta: deltaDisplay(data.bing_now.showing, data.bing_before.showing),
                    p1: data.sources.has_bing ? String(data.bing_now.page_one) : "—",
                    p1Delta: deltaDisplay(data.bing_now.page_one, data.bing_before.page_one),
                    avg: data.sources.has_bing && data.bing_now.position != null ? `#${data.bing_now.position.toFixed(1)}` : "—",
                    avgDelta: deltaDisplay(data.bing_now.position, data.bing_before.position, { lowerIsBetter: true }),
                    clk: data.sources.has_bing ? data.bing_now.clicks.toLocaleString("en-US") : "—",
                    clkDelta: deltaDisplay(data.bing_now.clicks, data.bing_before.clicks),
                    note: data.sources.has_bing ? `Bing Webmaster · weekly · through ${shortDate(data.sources.bing_through)}` : "No Bing data in range",
                  },
                  {
                    name: "SE Ranking",
                    dot: "#7a838c",
                    show: data.sources.ser_to ? String(serShowing) : "—",
                    showDelta: { text: `${data.sources.ser_tracked} tracked`, color: "#7a838c" },
                    p1: data.sources.ser_to ? String(serP1) : "—",
                    p1Delta: { text: "—", color: "#7a838c" },
                    avg: serAvg != null ? `#${serAvg}` : "—",
                    avgDelta: { text: "—", color: "#7a838c" },
                    clk: "—",
                    clkDelta: { text: "rank only", color: "#7a838c" },
                    note: data.sources.ser_to ? `SE Ranking · daily check · ${shortDate(data.sources.ser_to)}` : "No SE Ranking checks",
                  },
                ].map((e) => (
                  <div
                    key={e.name}
                    className="grid grid-cols-[minmax(0,1.2fr)_repeat(4,minmax(0,1fr))_minmax(0,1.6fr)] items-baseline gap-3 border-b border-[#f1f2f3] py-2.5 text-[13px] last:border-b-0"
                  >
                    <span className="flex items-center gap-2 font-semibold text-[#0a0c0f]">
                      <span className="h-2 w-2 rounded-full" style={{ background: e.dot }} />
                      {e.name}
                    </span>
                    <span className="tabular-nums">
                      <strong className="text-[#0a0c0f]">{e.show}</strong>{" "}
                      <span className="text-xs" style={{ color: e.showDelta.color }}>
                        {e.showDelta.text}
                      </span>
                    </span>
                    <span className="tabular-nums">
                      <strong className="text-[#0a0c0f]">{e.p1}</strong>{" "}
                      <span className="text-xs" style={{ color: e.p1Delta.color }}>
                        {e.p1Delta.text}
                      </span>
                    </span>
                    <span className="tabular-nums">
                      <strong className="text-[#0a0c0f]">{e.avg}</strong>{" "}
                      <span className="text-xs" style={{ color: e.avgDelta.color }}>
                        {e.avgDelta.text}
                      </span>
                    </span>
                    <span className="tabular-nums">
                      <strong className="text-[#0a0c0f]">{e.clk}</strong>{" "}
                      <span className="text-xs" style={{ color: e.clkDelta.color }}>
                        {e.clkDelta.text}
                      </span>
                    </span>
                    <span className="text-xs text-[#7a838c]">{e.note}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* 4. Rank matrix + By topic */}
            <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[1.5fr_1fr]">
              <div className="flex flex-col gap-2.5 rounded-xl border border-[#ececec] bg-white p-4">
                <div className="flex items-baseline justify-between gap-3">
                  <div>
                    <div className="font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">
                      Rank check, term by engine
                    </div>
                    <div className="text-xs text-[#7a838c]">Darker means a better position. Click a term to open it.</div>
                  </div>
                  {matrixTerms.length > 8 ? (
                    <button
                      type="button"
                      onClick={() => setMatrixShowAll((v) => !v)}
                      className="flex-none cursor-pointer text-xs font-semibold text-[#00857b] hover:underline"
                    >
                      {matrixShowAll ? "Show top 8" : `Show all ${matrixTerms.length}`}
                    </button>
                  ) : null}
                </div>

                <div className="flex flex-wrap gap-3 text-[11px] text-[#4a5560]">
                  {[
                    { t: "Top 3", bg: "#223540", border: "#223540" },
                    { t: "4–10", bg: "#c6f2ed", border: "#c6f2ed" },
                    { t: "11–20", bg: "#eef0f1", border: "#eef0f1" },
                    { t: "21+", bg: "#f8f8f8", border: "#e3e6e8" },
                  ].map((l) => (
                    <span key={l.t} className="inline-flex items-center gap-1.5">
                      <span className="h-2.5 w-2.5 rounded-[2px] border" style={{ background: l.bg, borderColor: l.border }} />
                      {l.t}
                    </span>
                  ))}
                </div>

                <div className="overflow-hidden rounded-[10px] border border-[#ececec]">
                  <div className="grid grid-cols-[minmax(0,1fr)_84px_84px_84px] border-b border-[#ececec] bg-[#fbfbfb] text-[11px] font-semibold text-[#4a5560]">
                    <span className="px-3 py-2">Term</span>
                    <span className="py-2 text-center">Google</span>
                    <span className="py-2 text-center">Bing</span>
                    <span className="py-2 text-center">SE Ranking</span>
                  </div>
                  {shownMatrix.map((m) => {
                    const cells = [
                      matrixCellStyle(hasGsc ? m.google.position : null),
                      matrixCellStyle(m.bing.position),
                      matrixCellStyle(m.ser.position),
                    ];
                    return (
                      <button
                        key={m.key}
                        type="button"
                        onClick={() => openTerm(m.key)}
                        className="grid w-full cursor-pointer grid-cols-[minmax(0,1fr)_84px_84px_84px] border-b border-[#f1f2f3] bg-white text-left text-[13px] last:border-b-0 hover:bg-[#f8f8f8]"
                      >
                        <span className="truncate px-3 py-2 text-[#171a22]">{m.term}</span>
                        {cells.map((c, idx) => (
                          <span
                            key={idx}
                            className="py-2 text-center text-xs font-semibold tabular-nums"
                            style={{ background: c.bg, color: c.fg }}
                          >
                            {c.text}
                          </span>
                        ))}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex flex-col gap-3 rounded-xl border border-[#ececec] bg-white p-4">
                <div>
                  <div className="font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">By topic</div>
                  <div className="text-xs text-[#7a838c]">Share of each topic&apos;s terms on Google page one</div>
                </div>
                <div className="space-y-1">
                  {topicStats.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => {
                        setTopicFilter(t.id);
                        setView("terms");
                      }}
                      className="-mx-1.5 flex w-[calc(100%+12px)] cursor-pointer flex-col gap-1.5 rounded-lg p-1.5 text-left text-[13px] hover:bg-[#f8f8f8]"
                    >
                      <div className="flex w-full items-baseline justify-between gap-2.5">
                        <span className="truncate font-semibold text-[#0a0c0f]">{t.name}</span>
                        <span className="flex-none whitespace-nowrap text-[#4a5560] tabular-nums">
                          <strong className="text-[#0a0c0f]">{hasGsc ? t.p1 : "—"}</strong> of {t.n} · avg {hasGsc ? t.avg : "—"}
                        </span>
                      </div>
                      <span className="block h-1.5 w-full overflow-hidden rounded bg-[#eef0f1]">
                        <span className="block h-full bg-[#00a99d]" style={{ width: `${hasGsc ? t.share : 0}%` }} />
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* 5. Biggest moves + Worth adding to the watchlist */}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="flex flex-col gap-1.5 rounded-xl border border-[#ececec] bg-white p-4">
                <div className="flex items-baseline justify-between gap-2">
                  <div className="font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">Biggest moves</div>
                  <span className="text-xs text-[#7a838c]">Half a position or more, either engine</span>
                </div>
                {mergedMoves.length === 0 ? (
                  <p className="py-3 text-[13px] text-[#7a838c]">No half-position moves in this period.</p>
                ) : (
                  mergedMoves.map((m) => {
                    const up = m.delta > 0;
                    return (
                      <button
                        key={`${m.key}-${m.src}`}
                        type="button"
                        onClick={() => openTerm(m.key)}
                        className="grid cursor-pointer grid-cols-[minmax(0,1fr)_56px_110px_64px] items-center gap-2.5 border-b border-[#f1f2f3] px-0.5 py-2 text-left text-[13px] last:border-b-0 hover:bg-[#f8f8f8]"
                      >
                        <span className="truncate font-semibold text-[#0a0c0f]">{m.term}</span>
                        <span className="justify-self-start rounded-full bg-[#f1f3f4] px-2 py-0 text-[10px] font-bold text-[#4a5560]">
                          {m.src}
                        </span>
                        <span className="text-right text-[#7a838c] tabular-nums">
                          #{m.from} → <strong className="text-[#0a0c0f]">#{m.to}</strong>
                        </span>
                        <span
                          className="text-right font-bold tabular-nums"
                          style={{ color: up ? "#00857b" : "oklch(0.52 0.17 25)" }}
                        >
                          {up ? "▲" : "▼"} {Math.abs(m.delta)}
                        </span>
                      </button>
                    );
                  })
                )}
              </div>

              <div className="flex flex-col gap-1.5 rounded-xl border border-[#ececec] bg-white p-4">
                <div className="flex items-baseline justify-between gap-2">
                  <div className="font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">
                    Worth adding to the watchlist
                  </div>
                  <span className="text-xs text-[#7a838c]">Search Console terms you don&apos;t track</span>
                </div>
                {!hasGsc ? (
                  <div className="py-2.5 text-[13px] text-[#7a838c]">
                    Needs Search Console. Suggestions appear once it&apos;s connected.
                  </div>
                ) : data.unsung_heroes.length === 0 ? (
                  <div className="py-2.5 text-[13px] text-[#7a838c]">No untracked high-impression queries found in this range.</div>
                ) : (
                  data.unsung_heroes.slice(0, 6).map((h) => {
                    const added = Boolean(addedHeroes[h.key]);
                    const busy = addingHeroKey === h.key;
                    return (
                      <div
                        key={h.key}
                        className="grid grid-cols-[minmax(0,1fr)_88px_60px_72px] items-center gap-2 border-b border-[#f1f2f3] px-0.5 py-2 text-[13px] last:border-b-0"
                      >
                        <span className="truncate font-semibold text-[#0a0c0f]">{h.query}</span>
                        <span className="text-right text-[#7a838c] tabular-nums">
                          {h.impressions.toLocaleString("en-US")} impr.
                        </span>
                        <span className="text-right text-[#7a838c] tabular-nums">
                          {h.position != null ? `#${h.position.toFixed(1)}` : "—"}
                        </span>
                        <button
                          type="button"
                          disabled={added || busy}
                          onClick={() => handleAddHero(h.query, h.key)}
                          className={`cursor-pointer justify-self-end rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                            added
                              ? "bg-[#e6f7f5] text-[#00665f]"
                              : "bg-[#223540] text-white hover:opacity-90"
                          }`}
                        >
                          {added ? "Added ✓" : busy ? "…" : "Add"}
                        </button>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* Terms split-view workbench */
        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          <aside className="flex w-full flex-none flex-col border-b border-[#e8e8e8] bg-white lg:w-[450px] lg:border-b-0 lg:border-r xl:w-[470px]">
            <div className="flex flex-col gap-2.5 border-b border-[#eef0f1] px-4 py-3">
              <div className="flex items-center gap-2 rounded-[10px] border border-[#e3e6e8] px-3">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#7a838c" strokeWidth="2.2" strokeLinecap="round" aria-hidden>
                  <circle cx="11" cy="11" r="7" />
                  <path d="m20 20-3.5-3.5" />
                </svg>
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Find a term"
                  aria-label="Find a term"
                  className="flex-1 bg-transparent py-2 text-[13px] text-[#171a22] placeholder:text-[#7a838c] focus:outline-none"
                />
              </div>

              <div className="flex flex-wrap gap-1.5">
                {topicFilter ? (
                  <button
                    type="button"
                    onClick={() => setTopicFilter("")}
                    className="flex-none cursor-pointer whitespace-nowrap rounded-full border border-[#00a99d] bg-[#e6f7f5] px-2.5 py-1 text-[11px] font-semibold text-[#00665f]"
                  >
                    {activeTopicName} ×
                  </button>
                ) : null}

                {(
                  [
                    { id: "all", label: "All", count: filterCounts.all },
                    { id: "p1", label: "Page one", count: filterCounts.p1 },
                    { id: "mv", label: "Moved", count: filterCounts.mv },
                    { id: "dis", label: "Sources differ", count: filterCounts.dis },
                    { id: "ns", label: "Not showing", count: filterCounts.ns },
                  ] as const
                ).map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setFilter(f.id)}
                    className={`flex-none cursor-pointer whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                      filter === f.id
                        ? "border-[#223540] bg-[#223540] text-white"
                        : "border-[#e3e6e8] bg-white text-[#4a5560] hover:text-[#0a0c0f]"
                    }`}
                  >
                    {f.label} <span className="font-medium opacity-65">{f.count}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-[minmax(0,1fr)_62px_62px_56px] gap-2 border-b border-[#f1f2f3] px-4 py-2 text-[10px] font-bold uppercase tracking-[0.1em] text-[#909a9f]">
              <span>Term</span>
              <span className="text-right">Google</span>
              <span className="text-right">Bing</span>
              <span className="text-right">Move</span>
            </div>

            <div className="flex-1 overflow-y-auto">
              {filteredTerms.length === 0 ? (
                <div className="px-4 py-8 text-center text-[13px] text-[#7a838c]">No terms match.</div>
              ) : (
                filteredTerms.map((t) => {
                  const selected = selectedTerm?.key === t.key;
                  const differ = isSourcesDiffer(t);
                  const mv = bestMove(t);
                  const gPos = hasGsc && t.google.position != null ? `#${t.google.position.toFixed(1)}` : "—";
                  const bPos = t.bing.position != null ? `#${t.bing.position.toFixed(1)}` : "—";
                  const mvTxt = mv != null && Math.abs(mv) >= 0.5 ? `${mv > 0 ? "▲" : "▼"} ${Math.abs(mv).toFixed(1)}` : "—";

                  return (
                    <button
                      key={t.key}
                      type="button"
                      onClick={() => setSelectedTermKey(t.key)}
                      style={selected ? { boxShadow: "inset 3px 0 0 #00a99d" } : undefined}
                      className={`grid w-full cursor-pointer grid-cols-[minmax(0,1fr)_62px_62px_56px] items-center gap-2 border-b border-[#f1f2f3] px-4 py-2.5 text-left transition-colors ${
                        selected ? "bg-[#eef8f7]" : "bg-white hover:bg-[#f8f8f8]"
                      }`}
                    >
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="truncate text-[13px] font-semibold text-[#0a0c0f]">{t.term}</span>
                          {differ ? (
                            <span
                              title="Google and Bing are 5+ positions apart"
                              className="rounded-full bg-[oklch(0.97_0.045_85)] px-1.5 py-0 text-[10px] font-bold text-[oklch(0.42_0.1_65)]"
                            >
                              Sources differ
                            </span>
                          ) : null}
                        </div>
                        <div className="truncate text-[11px] text-[#7a838c]">
                          {t.bucket}
                          {t.volume != null ? ` · ${t.volume.toLocaleString("en-US")}/mo` : ""}
                        </div>
                      </div>
                      <span
                        className={`text-right text-[13px] tabular-nums ${
                          hasGsc && t.google.position != null && t.google.position <= 10
                            ? "font-bold text-[#00857b]"
                            : "font-semibold text-[#4a5560]"
                        }`}
                      >
                        {gPos}
                      </span>
                      <span className="text-right text-[13px] text-[#4a5560] tabular-nums">{bPos}</span>
                      <span
                        className="text-right text-xs font-bold tabular-nums"
                        style={{
                          color:
                            mv != null && Math.abs(mv) >= 0.5
                              ? mv > 0
                                ? "#00857b"
                                : "oklch(0.52 0.17 25)"
                              : "#909a9f",
                        }}
                      >
                        {mvTxt}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </aside>

          {/* Right term detail */}
          {selectedTerm ? (
            <div className="min-w-0 flex-1 overflow-y-auto bg-[#f6f7f7]">
              <div className="flex flex-wrap items-start justify-between gap-5 border-b border-[#e8e8e8] bg-white px-7 py-4.5">
                <div className="min-w-0">
                  <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                    {selectedTerm.bucket}
                  </div>
                  <h2 className="font-[var(--font-heading)] text-[22px] font-bold text-[#0a0c0f]">
                    “{selectedTerm.term}”
                  </h2>
                  <div className="mt-0.5 text-[13px] text-[#4a5560]">
                    {selectedTerm.volume != null
                      ? `${selectedTerm.volume.toLocaleString("en-US")} searches a month`
                      : "Volume not measured"}
                    {detail?.pages[0]?.url ? (
                      <>
                        {" "}
                        · ranking page{" "}
                        <a
                          href={detail.pages[0].url}
                          target="_blank"
                          rel="noreferrer"
                          className="font-semibold text-[#00a99d] hover:underline"
                        >
                          {shortPath(detail.pages[0].url)}
                        </a>
                      </>
                    ) : selectedTerm.ser.url ? (
                      <>
                        {" "}
                        · ranking page{" "}
                        <a
                          href={selectedTerm.ser.url}
                          target="_blank"
                          rel="noreferrer"
                          className="font-semibold text-[#00a99d] hover:underline"
                        >
                          {shortPath(selectedTerm.ser.url)}
                        </a>
                      </>
                    ) : null}
                  </div>
                </div>

                <div className="flex flex-none flex-col items-end gap-2">
                  <Link
                    href={`/${client.slug}/engine?term=${encodeURIComponent(selectedTerm.term)}`}
                    className="rounded-full bg-[#223540] px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-[#00a99d]"
                  >
                    Diagnose in Decision engine
                  </Link>
                  <button
                    type="button"
                    onClick={() => setRemovedKeys((prev) => ({ ...prev, [selectedTerm.key]: true }))}
                    className="cursor-pointer text-xs font-semibold text-[#7a838c] hover:text-[#171a22]"
                  >
                    Remove from watchlist
                  </button>
                </div>
              </div>

              <div className="space-y-3.5 px-7 py-4.5 pb-8">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  {/* Google cell */}
                  <div className="flex flex-col gap-1 rounded-xl border border-[#ececec] bg-white px-4 py-3.5">
                    <div className="text-xs font-semibold text-[#7a838c]">Google position</div>
                    <div className="font-[var(--font-heading)] text-[26px] font-bold text-[#0a0c0f] tabular-nums">
                      {hasGsc && selectedTerm.google.position != null
                        ? `#${selectedTerm.google.position.toFixed(1)}`
                        : "—"}
                    </div>
                    {(() => {
                      const d = hasGsc
                        ? deltaDisplay(selectedTerm.google.position, selectedTerm.google.position_before, { lowerIsBetter: true })
                        : { text: "no data", color: "#7a838c" };
                      return (
                        <div className="text-xs font-semibold" style={{ color: d.color }}>
                          {d.text}
                        </div>
                      );
                    })()}
                    <div className="text-xs text-[#7a838c] tabular-nums">
                      {hasGsc
                        ? `${selectedTerm.google.impressions.toLocaleString("en-US")} impr · ${selectedTerm.google.clicks.toLocaleString("en-US")} clicks`
                        : "Search Console not connected"}
                    </div>
                  </div>

                  {/* Bing cell */}
                  <div className="flex flex-col gap-1 rounded-xl border border-[#ececec] bg-white px-4 py-3.5">
                    <div className="text-xs font-semibold text-[#7a838c]">Bing position</div>
                    <div className="font-[var(--font-heading)] text-[26px] font-bold text-[#0a0c0f] tabular-nums">
                      {selectedTerm.bing.position != null ? `#${selectedTerm.bing.position.toFixed(1)}` : "—"}
                    </div>
                    {(() => {
                      const d = deltaDisplay(selectedTerm.bing.position, selectedTerm.bing.position_before, { lowerIsBetter: true });
                      return (
                        <div className="text-xs font-semibold" style={{ color: d.color }}>
                          {d.text}
                        </div>
                      );
                    })()}
                    <div className="text-xs text-[#7a838c]">
                      {data.sources.bing_through ? `Latest week: ${shortDate(data.sources.bing_through)}` : "No Bing data"}
                    </div>
                  </div>

                  {/* SE Ranking cell */}
                  <div className="flex flex-col gap-1 rounded-xl border border-[#ececec] bg-white px-4 py-3.5">
                    <div className="text-xs font-semibold text-[#7a838c]">SE Ranking check</div>
                    <div className="font-[var(--font-heading)] text-[26px] font-bold text-[#0a0c0f] tabular-nums">
                      {selectedTerm.ser.position != null ? `#${selectedTerm.ser.position}` : "—"}
                    </div>
                    {(() => {
                      const d = deltaDisplay(selectedTerm.ser.position, selectedTerm.ser.position_start, { lowerIsBetter: true });
                      return (
                        <div className="text-xs font-semibold" style={{ color: d.color }}>
                          {d.text}
                        </div>
                      );
                    })()}
                    <div className="text-xs text-[#7a838c]">
                      {data.sources.ser_to ? `Checked ${shortDate(data.sources.ser_to)}` : "Not tracked"}
                    </div>
                  </div>
                </div>

                {isSourcesDiffer(selectedTerm) ? (
                  <div className="rounded-[10px] bg-[oklch(0.97_0.045_85)] px-3.5 py-2.5 text-[13px] text-[#171a22]">
                    <strong className="text-[oklch(0.42_0.1_65)]">
                      Google and Bing disagree
                      {posGap(selectedTerm) != null ? ` by ${posGap(selectedTerm)!.toFixed(1)} positions` : ""}.
                    </strong>{" "}
                    This is worth a look, not an error in either source. It often means the engines rank different pages for this term.
                  </div>
                ) : null}

                <TermWeeklyChart weeks={data.weeks} trend={selectedTerm.trend} />

                {detailLoading ? (
                  <div className="rounded-xl border border-[#ececec] bg-white p-4 text-xs text-[#7a838c]">
                    Loading ranking pages, competitors, and SERP snapshot…
                  </div>
                ) : (
                  <>
                    {detail && (detail.pages.length > 0 || detail.competitors.length > 0) ? (
                      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                        {detail.pages.length > 0 ? (
                          <div className="rounded-xl border border-[#ececec] bg-white p-4">
                            <div className="font-[var(--font-heading)] text-[14px] font-bold text-[#0a0c0f]">
                              Ranking pages (Google)
                            </div>
                            <div className="mt-2 divide-y divide-[#f1f2f3]">
                              {detail.pages.slice(0, 5).map((p) => (
                                <div key={p.url} className="flex items-center justify-between gap-2 py-1.5 text-xs">
                                  <a
                                    href={p.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="truncate text-[#171a22] hover:text-[#00857b] hover:underline"
                                  >
                                    {shortPath(p.url)}
                                  </a>
                                  <span className="flex-none text-[#7a838c] tabular-nums">
                                    {p.position != null ? `#${p.position.toFixed(1)}` : "—"} · {p.clicks} clk
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        {detail.competitors.length > 0 ? (
                          <div className="rounded-xl border border-[#ececec] bg-white p-4">
                            <div className="font-[var(--font-heading)] text-[14px] font-bold text-[#0a0c0f]">
                              Top SERP competitors
                            </div>
                            <div className="mt-2 divide-y divide-[#f1f2f3]">
                              {detail.competitors.slice(0, 5).map((c) => (
                                <div key={`${c.domain}-${c.position}`} className="flex items-center justify-between gap-2 py-1.5 text-xs">
                                  <span className="truncate font-medium text-[#171a22]">{c.domain}</span>
                                  <span className="flex-none font-semibold text-[#4a5560] tabular-nums">#{c.position}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    ) : null}

                    {detail ? (
                      <div className="rounded-xl border border-[#ececec] bg-white p-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                              DataForSEO SERP snapshot
                            </div>
                            <div className="font-[var(--font-heading)] text-[15px] font-bold text-[#0a0c0f]">
                              Live search results &amp; People Also Ask
                            </div>
                          </div>
                          {detail.serp ? (
                            <div className="flex flex-wrap items-center gap-1.5">
                              {detail.serp.reading?.read ? (
                                <span className="rounded-full bg-[#e6f7f5] px-2.5 py-0.5 text-[11px] font-semibold text-[#00665f]">
                                  Intent: {detail.serp.reading.name}
                                </span>
                              ) : null}
                              <span className="rounded-full bg-[#f1f3f4] px-2.5 py-0.5 text-[11px] font-semibold text-[#4a5560]">
                                Pulled {shortDate(detail.serp.pulled_on)}
                              </span>
                            </div>
                          ) : null}
                        </div>

                        {(() => {
                          const serp = detail.serp;
                          const featureList = Array.from(
                            new Set([...(serp?.features ?? []), ...(serp?.item_types ?? [])].filter(Boolean)),
                          );
                          const holderEntries = Object.entries(serp?.holders ?? {}).filter(
                            ([, domains]) => Array.isArray(domains) && domains.length > 0,
                          );
                          const hasContent =
                            Boolean(serp) &&
                            (featureList.length > 0 ||
                              holderEntries.length > 0 ||
                              (serp?.questions.length ?? 0) > 0 ||
                              (serp?.results.length ?? 0) > 0);

                          if (!serp || !hasContent) {
                            return (
                              <div className="mt-3 rounded-[10px] border border-dashed border-[#d3d7d9] bg-[#f8f8f8] px-4 py-3 text-xs text-[#4a5560]">
                                No DataForSEO SERP snapshot has been pulled for &ldquo;{selectedTerm.term}&rdquo; yet. Open it in the Decision engine to fetch live organic results, SERP features, and People Also Ask questions.
                              </div>
                            );
                          }

                          return (
                            <div className="mt-3 space-y-3.5">
                              {featureList.length > 0 ? (
                                <div>
                                  <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                                    SERP features
                                  </div>
                                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                                    {featureList.map((f) => (
                                      <span
                                        key={f}
                                        className="rounded-full bg-[#e6f7f5] px-2.5 py-0.5 text-[11px] font-semibold text-[#00665f]"
                                      >
                                        {f.replaceAll("_", " ")}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              ) : null}

                              {holderEntries.length > 0 ? (
                                <div>
                                  <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                                    Feature holders
                                  </div>
                                  <div className="mt-1.5 flex flex-wrap gap-2">
                                    {holderEntries.map(([feature, domains]) => (
                                      <div
                                        key={feature}
                                        className="rounded-[10px] border border-[#ececec] bg-[#f8f8f8] px-3 py-1.5 text-xs"
                                      >
                                        <span className="font-semibold text-[#171a22]">
                                          {feature.replaceAll("_", " ")}:
                                        </span>{" "}
                                        <span className="text-[#4a5560]">{domains.join(", ")}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ) : null}

                              {serp.questions.length > 0 ? (
                                <div>
                                  <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                                    People Also Ask ({serp.questions.length})
                                  </div>
                                  <ul className="mt-1.5 space-y-1.5">
                                    {serp.questions.map((q) => (
                                      <li
                                        key={q}
                                        className="flex items-start gap-2 rounded-[10px] border border-[#ececec] bg-[#f8f8f8] px-3 py-2 text-xs text-[#171a22]"
                                      >
                                        <span className="mt-0.5 rounded-full bg-[#e6f7f5] px-2 py-0 text-[10px] font-bold text-[#00665f]">
                                          PAA
                                        </span>
                                        <span>{q}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              ) : null}

                              {serp.results.length > 0 ? (
                                <div>
                                  <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                                    Top organic results ({serp.results.length})
                                  </div>
                                  <div className="mt-1.5 overflow-hidden rounded-[10px] border border-[#ececec]">
                                    {serp.results.slice(0, 10).map((r) => (
                                      <div
                                        key={`${r.rank}-${r.url}`}
                                        className="flex items-start gap-3 border-b border-[#f1f2f3] bg-white px-3 py-2.5 text-xs last:border-b-0"
                                      >
                                        <span className="flex h-5 w-5 flex-none items-center justify-center rounded-full bg-[#223540] text-[10px] font-bold text-white tabular-nums">
                                          {r.rank}
                                        </span>
                                        <div className="min-w-0 flex-1">
                                          <a
                                            href={r.url}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="font-semibold text-[#0a0c0f] hover:text-[#00857b] hover:underline"
                                          >
                                            {r.title || r.domain}
                                          </a>
                                          <div className="truncate text-[11px] text-[#7a838c]">
                                            {r.domain} · {r.url}
                                          </div>
                                          {r.snippet ? (
                                            <p className="mt-0.5 line-clamp-2 text-[11px] text-[#4a5560]">{r.snippet}</p>
                                          ) : null}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ) : null}
                            </div>
                          );
                        })()}
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center p-8 text-sm text-[#4a5560]">
              Select a term on the left to inspect its rankings.
            </div>
          )}
        </div>
      )}

      <VisibilityCheckDrawer
        open={checkDrawerOpen}
        clientId={client.id}
        clientSlug={client.slug}
        defaultSummary={`Visibility check (${fullRange(from, to)})`}
        onClose={() => setCheckDrawerOpen(false)}
        onSaved={() => {
          setCheckLogged(true);
          router.refresh();
        }}
      />
    </section>
  );
}
