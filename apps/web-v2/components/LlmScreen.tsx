"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { llmResponsesAction, saveLlmSettingsAction, startLlmRunAction } from "@/app/(app)/[clientSlug]/llm/actions";
import type { Client } from "@/lib/api";
import type { LlmOverview, LlmResponseRow, LlmRunInfo, LlmSettings, Pair, QueryRow } from "@/lib/llm";

type Tab = "overview" | "queries" | "sov" | "run" | "setup";

const pct = (n: number | null | undefined) => (n == null ? "–" : `${(n * 100).toFixed(0)}%`);
const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString());
const day = (iso: string) => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

function Delta({ pair, percent = false }: { pair: Pair; percent?: boolean }) {
  if (pair.delta == null) return <span className="text-xs text-[var(--text-tertiary)]">first run</span>;
  const shown = percent ? `${Math.abs(pair.delta * 100).toFixed(0)} pts` : Math.abs(pair.delta).toLocaleString();
  if (pair.delta === 0) return <span className="text-xs text-[var(--text-secondary)]">no change</span>;
  return (
    <span className={`text-xs font-semibold ${pair.delta > 0 ? "text-green-700" : "text-red-700"}`}>
      {pair.delta > 0 ? "▲" : "▼"} {shown}
    </span>
  );
}

function Stat({ label, value, pair, percent }: { label: string; value: string; pair?: Pair; percent?: boolean }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums">{value}</div>
      {pair ? <Delta pair={pair} percent={percent} /> : null}
    </div>
  );
}

const CODE_STYLE: Record<string, string> = {
  "C+M": "bg-green-100 text-green-800",
  C: "bg-blue-100 text-blue-800",
  M: "bg-amber-100 text-amber-800",
  "—": "bg-[var(--bg)] text-[var(--text-tertiary)]",
};

function Mover({ row }: { row: QueryRow }) {
  return (
    <li className="flex items-start justify-between gap-3 border-t border-[var(--border)] py-2 first:border-t-0">
      <div className="min-w-0">
        <div className="text-sm font-medium">{row.query}</div>
        <div className="text-xs text-[var(--text-tertiary)]">{row.topic_cluster ?? "Uncategorized"}</div>
      </div>
      <span className={`whitespace-nowrap text-xs font-semibold ${(row.change ?? 0) > 0 ? "text-green-700" : "text-red-700"}`}>
        {(row.change ?? 0) > 0 ? "+" : ""}
        {row.change} ({row.previous_score}→{row.score})
      </span>
    </li>
  );
}

function Overview({ data }: { data: LlmOverview }) {
  const s = data.summary!;
  const trend = data.trend ?? [];
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Brand mentions" value={num(s.mentions.current)} pair={s.mentions} />
        <Stat label="Citations" value={num(s.citations.current)} pair={s.citations} />
        <Stat label="Average visibility rate" value={pct(s.visibility_rate.current)} pair={s.visibility_rate} percent />
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
          <div className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">Last run</div>
          <div className="mt-1 text-lg font-bold">{day(data.run!.started_at)}</div>
          <div className="text-xs text-[var(--text-secondary)]">
            {data.run!.total_calls} answers{data.run!.total_errors ? `, ${data.run!.total_errors} failed` : ""}
            {data.run!.estimated_cost_usd != null ? `, about $${data.run!.estimated_cost_usd.toFixed(2)}` : ""}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {(["improved", "declined"] as const).map((kind) => (
          <div key={kind} className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <h3 className="text-sm font-semibold">{kind === "improved" ? "Top improvements" : "Top declines"}</h3>
            {data.movers![kind].length === 0 ? (
              <p className="mt-2 text-sm text-[var(--text-tertiary)]">
                {data.previous_run ? "No prompt moved this way since the last run." : "This is the first run, so there is nothing to compare with yet."}
              </p>
            ) : (
              <ul className="mt-2">{data.movers![kind].map((r) => <Mover key={r.query} row={r} />)}</ul>
            )}
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
        <h3 className="text-sm font-semibold">Performance by platform</h3>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
              <tr>
                <th className="py-1 pr-3 font-medium">Platform</th>
                <th className="px-3 py-1 text-right font-medium">Visibility rate</th>
                <th className="px-3 py-1 text-right font-medium">Mentions</th>
                <th className="px-3 py-1 text-right font-medium">Citations</th>
                <th className="px-3 py-1 text-right font-medium">Avg rank</th>
                <th className="py-1 pl-3 font-medium">Answers</th>
              </tr>
            </thead>
            <tbody>
              {data.platforms!.map((p) => (
                <tr key={p.platform} className="border-t border-[var(--border)]">
                  <td className="py-2 pr-3 font-medium">{p.platform}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{pct(p.visibility_rate.current)} <Delta pair={p.visibility_rate} percent /></td>
                  <td className="px-3 py-2 text-right tabular-nums">{p.mentions.current} <Delta pair={p.mentions} /></td>
                  <td className="px-3 py-2 text-right tabular-nums">{p.citations.current} <Delta pair={p.citations} /></td>
                  <td className="px-3 py-2 text-right tabular-nums">{p.avg_brand_rank.current ?? "–"}</td>
                  <td className="py-2 pl-3 text-xs text-[var(--text-secondary)]">
                    {p.by_type.cited_mentioned} cited + mentioned, {p.by_type.cited} cited, {p.by_type.mentioned} mentioned, {p.by_type.not_visible} not visible
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {trend.length > 1 ? (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <h3 className="text-sm font-semibold">Visibility rate by run</h3>
          <div className="mt-3 flex items-end gap-2" style={{ height: "6rem" }}>
            {trend.map((t) => (
              <div key={t.run_id} className="flex flex-1 flex-col items-center justify-end gap-1">
                <span className="text-xs tabular-nums">{pct(t.visibility_rate)}</span>
                <div className="w-full rounded-t bg-[var(--brand-teal)]" style={{ height: `${Math.max(4, t.visibility_rate * 70)}px` }} />
                <span className="text-[0.65rem] text-[var(--text-tertiary)]">{new Date(t.started_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {data.other_brands && data.other_brands.length > 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">
          <span className="font-semibold">Also named in answers, not tracked:</span> {data.other_brands.map((b) => `${b.name} (${b.count})`).join(", ")}. Add one under Setup to count it in share of voice.
        </p>
      ) : null}
      {data.errors && data.errors.length > 0 ? (
        <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          <span className="font-semibold">Some answers failed:</span> {data.errors.map((e) => `${e.platform}, ${e.count}×: ${e.message}`).join(" · ")}
        </div>
      ) : null}
    </div>
  );
}

function Queries({ data }: { data: LlmOverview }) {
  const platforms = Array.from(new Set(data.queries!.flatMap((q) => Object.keys(q.by_platform)))).sort();
  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <p className="mb-3 text-xs text-[var(--text-tertiary)]">
        C+M = cited and mentioned, C = cited, M = mentioned, — = not visible. Score is 2 for cited and mentioned, 1 for either, 0 for neither, summed over platforms.
      </p>
      <table className="w-full min-w-[44rem] text-left text-sm">
        <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
          <tr>
            <th className="py-1 pr-3 font-medium">Prompt</th>
            {platforms.map((p) => (
              <th key={p} className="px-2 py-1 text-center font-medium">{p}</th>
            ))}
            <th className="px-3 py-1 text-right font-medium">Score</th>
            <th className="px-3 py-1 text-right font-medium">Avg rank</th>
            <th className="py-1 pl-3 font-medium">Named most often</th>
          </tr>
        </thead>
        <tbody>
          {data.queries!.map((q) => (
            <tr key={q.query} className="border-t border-[var(--border)] align-top">
              <td className="min-w-[14rem] py-2 pr-3">
                <div className="font-medium">{q.query}</div>
                <div className="text-xs text-[var(--text-tertiary)]">{q.topic_cluster ?? "Uncategorized"}</div>
              </td>
              {platforms.map((p) => (
                <td key={p} className="px-2 py-2 text-center">
                  <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${CODE_STYLE[q.by_platform[p] ?? "—"]}`}>{q.by_platform[p] ?? "—"}</span>
                </td>
              ))}
              <td className="px-3 py-2 text-right tabular-nums">
                {q.score}/{q.max_score}
                {q.change != null && q.change !== 0 ? <span className={`ml-1 text-xs font-semibold ${q.change > 0 ? "text-green-700" : "text-red-700"}`}>{q.change > 0 ? "+" : ""}{q.change}</span> : null}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{q.avg_brand_rank ?? "–"}</td>
              <td className="py-2 pl-3 text-xs text-[var(--text-secondary)]">{q.top_competitors.map((c) => `${c.name} (${c.count})`).join(", ") || "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ShareOfVoice({ data }: { data: LlmOverview }) {
  const clusters = Array.from(new Set(data.share_of_voice!.map((r) => r.topic_cluster)));
  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--text-secondary)]">
        Share of voice is the share of a topic&apos;s answers that name each brand. The topic is the watchlist bucket the prompt belongs to.
      </p>
      {clusters.map((cluster) => {
        const rows = data.share_of_voice!.filter((r) => r.topic_cluster === cluster);
        return (
          <div key={cluster} className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <h3 className="text-sm font-semibold">
              {cluster} <span className="font-normal text-[var(--text-tertiary)]">· {rows[0].responses} answers</span>
            </h3>
            <ul className="mt-3 space-y-2">
              {rows.map((r) => (
                <li key={r.brand} className="flex items-center gap-3 text-sm">
                  <span className={`w-40 shrink-0 truncate ${r.is_self ? "font-bold" : ""}`}>{r.brand}</span>
                  <div className="h-3 flex-1 rounded bg-[var(--bg)]">
                    <div className={`h-3 rounded ${r.is_self ? "bg-[var(--brand-teal)]" : "bg-[var(--text-tertiary)]"}`} style={{ width: `${Math.min(100, r.share.current * 100)}%` }} />
                  </div>
                  <span className="w-12 text-right tabular-nums">{pct(r.share.current)}</span>
                  <span className="w-20 text-right"><Delta pair={r.share} percent /></span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      {clusters.length === 0 ? <p className="text-sm text-[var(--text-tertiary)]">No answers to count yet.</p> : null}
    </div>
  );
}

function FullRun({ client, run }: { client: Client; run: LlmRunInfo }) {
  const [rows, setRows] = useState<LlmResponseRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [platform, setPlatform] = useState("all");
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    setRows(null);
    llmResponsesAction(client.id, run.id).then((r) => (r.ok ? setRows(r.value) : setError(r.error)));
  }, [client.id, run.id]);
  if (error) return <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>;
  if (!rows) return <p className="text-sm text-[var(--text-secondary)]">Loading the run…</p>;
  const platforms = Array.from(new Set(rows.map((r) => r.platform)));
  const shown = rows.filter((r) => platform === "all" || r.platform === platform);
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <label className="text-sm">
        <span className="font-semibold">Platform</span>
        <select value={platform} onChange={(e) => setPlatform(e.target.value)} className="ml-2 rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm">
          <option value="all">All ({rows.length})</option>
          {platforms.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </label>
      <ul className="mt-3 divide-y divide-[var(--border)]">
        {shown.map((r) => {
          const key = `${r.query}|${r.platform}`;
          return (
            <li key={key} className="py-3">
              <button type="button" onClick={() => setOpen(open === key ? null : key)} className="flex w-full items-start justify-between gap-3 text-left">
                <span>
                  <span className="block text-sm font-medium">{r.query}</span>
                  <span className="text-xs text-[var(--text-tertiary)]">{r.platform} · {r.topic_cluster ?? "Uncategorized"}{r.position && r.position !== "Not mentioned" ? ` · ${r.position}` : ""}</span>
                </span>
                <span className={`whitespace-nowrap rounded px-2 py-0.5 text-xs font-semibold ${r.visibility === "Error" ? "bg-red-50 text-red-800" : CODE_STYLE[r.visibility === "Cited + Mentioned" ? "C+M" : r.visibility === "Cited" ? "C" : r.visibility === "Mentioned" ? "M" : "—"]}`}>{r.visibility}</span>
              </button>
              {open === key ? (
                <div className="mt-2 space-y-2 text-sm">
                  {r.error ? <p className="text-red-800">{r.error}</p> : <p className="whitespace-pre-wrap text-[var(--text-secondary)]">{r.answer}</p>}
                  <p className="text-xs text-[var(--text-tertiary)]">
                    {r.competitors.length ? `Competitors named: ${r.competitors.join(", ")}. ` : ""}
                    {r.other_brands.length ? `Other brands: ${r.other_brands.join(", ")}. ` : ""}
                    {r.cited_urls.length ? `Cited: ${r.cited_urls.join(", ")}` : ""}
                  </p>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Setup({ client, settings }: { client: Client; settings: LlmSettings }) {
  const router = useRouter();
  const [brand, setBrand] = useState(settings.brand_name);
  const [patterns, setPatterns] = useState(settings.brand_patterns.join(", "));
  const [comps, setComps] = useState(settings.competitors.map((c) => ({ ...c, text: c.patterns.join(", ") })));
  const [message, setMessage] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const split = (t: string) => t.split(",").map((p) => p.trim()).filter(Boolean);
  const save = () =>
    start(async () => {
      const r = await saveLlmSettingsAction(client.id, {
        brand_name: brand,
        brand_patterns: split(patterns),
        competitors: comps.map((c) => ({ domain: c.domain, name: c.name, patterns: split(c.text) })),
      });
      setMessage(r.ok ? "Saved." : r.error);
      if (r.ok) router.refresh();
    });
  const input = "w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm";
  return (
    <div className="max-w-3xl space-y-6">
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 text-sm">
        <h3 className="font-semibold">What a run asks</h3>
        <p className="mt-1 text-[var(--text-secondary)]">
          {settings.prompts} paired AI prompts from the watchlist, across {settings.clusters.length} topics, on{" "}
          {settings.platforms.filter((p) => p.enabled).map((p) => p.name).join(", ") || "no platform yet"}
          {settings.calls_per_run ? `: ${settings.calls_per_run} answers a run.` : "."}
        </p>
        <ul className="mt-2 flex flex-wrap gap-2 text-xs">
          {settings.platforms.map((p) => (
            <li key={p.key} className={`rounded px-2 py-0.5 font-semibold ${p.enabled ? "bg-green-100 text-green-800" : "bg-[var(--bg)] text-[var(--text-tertiary)]"}`}>
              {p.name} {p.enabled ? "ready" : "no API key"}
            </li>
          ))}
        </ul>
        {settings.platforms.some((p) => !p.enabled) ? (
          <p className="mt-2 text-xs text-[var(--text-tertiary)]">
            A platform is skipped until its key is in the API&apos;s environment: OPENAI_API_KEY, PERPLEXITY_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY. The Anthropic key also finds other brands named in answers.
          </p>
        ) : null}
      </div>
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 text-sm">
        <h3 className="font-semibold">How to spot the brand</h3>
        <label className="mt-3 block"><span className="font-semibold">Brand name</span><input value={brand} onChange={(e) => setBrand(e.target.value)} className={`mt-1 ${input}`} /></label>
        <label className="mt-3 block">
          <span className="font-semibold">Names to look for</span>
          <input value={patterns} onChange={(e) => setPatterns(e.target.value)} className={`mt-1 ${input}`} />
          <span className="mt-1 block text-xs text-[var(--text-tertiary)]">Comma separated. A name counts only as a whole word, and the site {settings.domain} counts as a citation.</span>
        </label>
        {comps.length ? <h3 className="mt-5 font-semibold">Competitors</h3> : <p className="mt-4 text-xs text-[var(--text-tertiary)]">Add competitor domains in the client&apos;s settings and they appear here.</p>}
        {comps.map((c, i) => (
          <div key={c.domain} className="mt-2 grid gap-2 sm:grid-cols-[10rem_1fr_1fr]">
            <span className="self-center text-xs text-[var(--text-secondary)]">{c.domain}</span>
            <input value={c.name} onChange={(e) => setComps(comps.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} className={input} aria-label={`${c.domain} name`} />
            <input value={c.text} onChange={(e) => setComps(comps.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} className={input} aria-label={`${c.domain} names to look for`} />
          </div>
        ))}
        <div className="mt-4 flex items-center gap-3">
          <button type="button" onClick={save} disabled={pending} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Save</button>
          {message ? <span className="text-sm text-[var(--text-secondary)]">{message}</span> : null}
        </div>
      </div>
    </div>
  );
}

export function LlmScreen({ client, overview, settings, error }: { client: Client; overview: LlmOverview | null; settings: LlmSettings | null; error: string | null }) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("overview");
  const [pending, start] = useTransition();
  const [runError, setRunError] = useState<string | null>(null);
  const [queued, setQueued] = useState(false);
  const running = Boolean(overview?.running) || queued;

  // A run takes minutes; look again until it lands.
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => router.refresh(), 8000);
    return () => clearInterval(t);
  }, [running, router]);
  useEffect(() => {
    if (overview?.running === null && queued && overview.runs.length) setQueued(false);
  }, [overview, queued]);

  const startRun = () =>
    start(async () => {
      setRunError(null);
      const r = await startLlmRunAction(client.id);
      if (r.ok) {
        setQueued(true);
        router.refresh();
      } else setRunError(r.error);
    });

  const run = overview?.run ?? null;
  const tabs: [Tab, string][] = [["overview", "Overview"], ["queries", "Query summary"], ["sov", "Share of voice"], ["run", "Full run"], ["setup", "Setup"]];

  return (
    <section className="max-w-6xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">LLM visibility</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Whether ChatGPT, Perplexity, Gemini and Claude name {client.client_name} and cite its site when asked the watchlist&apos;s prompts.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {overview && overview.runs.length > 1 ? (
            <select
              value={run?.id ?? ""}
              onChange={(e) => router.push(`/${client.slug}/llm?run=${e.target.value}`)}
              className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm"
              aria-label="Run"
            >
              {overview.runs.map((r) => <option key={r.id} value={r.id}>{day(r.started_at)}</option>)}
            </select>
          ) : null}
          <button type="button" onClick={startRun} disabled={pending || running} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
            {running ? "Running…" : "Run now"}
          </button>
        </div>
      </header>

      {running ? <p className="rounded-lg bg-[var(--bg)] p-3 text-sm text-[var(--text-secondary)]">A run is queued or in progress. It takes a few minutes and this page updates when it lands.</p> : null}
      {runError ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{runError}</p> : null}
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}

      <nav className="flex flex-wrap gap-2" aria-label="LLM visibility views">
        {tabs.map(([id, label]) => (
          <button key={id} type="button" onClick={() => setTab(id)} aria-current={tab === id ? "page" : undefined}
            className={`rounded-full border px-4 py-1.5 text-sm font-semibold ${tab === id ? "border-[var(--brand-teal)] bg-[var(--brand-teal)] text-white" : "border-[var(--border)]"}`}>
            {label}
          </button>
        ))}
      </nav>

      {tab === "setup" ? (
        settings ? <Setup client={client} settings={settings} /> : <p className="text-sm text-[var(--text-secondary)]">Setup could not be loaded.</p>
      ) : !run ? (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-sm">
          <h2 className="font-semibold">No run yet</h2>
          <p className="mt-1 text-[var(--text-secondary)]">
            {settings && settings.prompts === 0
              ? "The watchlist has no paired AI prompts, so there is nothing to ask. Import them with the watchlist."
              : settings && settings.calls_per_run === 0
                ? "No AI platform has an API key on this install. Setup shows which are missing."
                : `Run now asks ${settings?.prompts ?? 0} prompts on each platform (${settings?.calls_per_run ?? 0} answers). Runs then repeat monthly.`}
          </p>
        </div>
      ) : tab === "overview" ? (
        <Overview data={overview!} />
      ) : tab === "queries" ? (
        <Queries data={overview!} />
      ) : tab === "sov" ? (
        <ShareOfVoice data={overview!} />
      ) : (
        <FullRun client={client} run={run} />
      )}
    </section>
  );
}
