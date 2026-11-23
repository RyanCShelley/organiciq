"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { ctrPageAction, ctrTitleAction } from "@/app/(app)/[clientSlug]/ctr/actions";
import { WeeklyLine } from "@/components/bi/Charts";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import { presets } from "@/lib/bi";
import type { Ctr, CtrDepth, CtrDetail, CtrPage, CtrSearch, CtrWindow } from "@/lib/ctr";
import { monthLabel } from "@/lib/focus";

const card = "rounded-xl border border-[var(--border)] bg-[var(--surface)]";
const th = "px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]";
const td = "px-3 py-2 tabular-nums";
const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString());
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className={`${card} p-4`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-3xl font-bold tabular-nums">{value}</div>
      {note ? <div className="mt-1 text-xs text-[var(--text-secondary)]">{note}</div> : null}
    </div>
  );
}

function Window({ w }: { w: CtrWindow }) {
  return w ? <span className="tabular-nums">{w.ctr}% ({num(w.clicks)} of {num(w.impressions)})</span> : <span className="text-[var(--text-tertiary)]">too little data</span>;
}

const DEPTH: Record<CtrDepth, string> = { quick: "Quick (Sonnet 5.5)", deep: "Deep dive (Opus 5.5)", deepest: "Deepest (Fable 5.1)" };

function PagePane({ client, url, from, to }: { client: Client; url: string; from: string; to: string }) {
  const [d, setD] = useState<CtrDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [depth, setDepth] = useState<CtrDepth>("quick");
  const [copied, setCopied] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const load = () => ctrPageAction(client.id, url, from, to).then((r) => (r.ok ? setD(r.value) : setError(r.error)));
  useEffect(() => {
    setD(null);
    setError(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client.id, url, from, to]);
  const running = d?.title_draft?.status === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);
  const write = () =>
    start(async () => {
      setError(null);
      const r = await ctrTitleAction(client.id, url, from, to, depth);
      if (!r.ok) setError(r.error);
      else await load();
    });
  const copy = (key: string, text: string) => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(key);
      setTimeout(() => setCopied(null), 1500);
    });
  };
  const draft = d?.title_draft;
  const descriptionNow = draft?.description_now ?? d?.description ?? null;
  const descriptionNowLen = draft?.description_now_length ?? d?.description_length ?? null;
  return (
    <div className="space-y-4 text-sm">
      <p className="break-all font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">{url}</p>
      {error ? <p role="alert" className="rounded-xl border border-[oklch(0.88_0.06_25)] bg-[oklch(0.965_0.025_25)] px-3.5 py-2.5 text-xs font-semibold text-[oklch(0.48_0.17_25)]">{error}</p> : null}
      {!d && !error ? <p className="text-[#4a5560]"><Spinner />Reading the page…</p> : null}
      {d ? (
        <>
          <div className="rounded-xl border border-[#ececec] bg-[#f8f8f8] p-3.5 text-xs">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
              Current title{d.title_length != null ? ` · ${d.title_length}/60 chars${d.title_length > 60 ? " (may be cut off)" : ""}` : ""}
            </div>
            <div className="mt-1 mb-3 text-[13px] text-[#0a0c0f]">{d.title || <span className="text-[#7a838c]">none found in the crawl</span>}</div>
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
              Current meta description{descriptionNowLen != null ? ` · ${descriptionNowLen}/160 chars${descriptionNowLen > 160 ? " (may be cut off)" : descriptionNowLen < 70 ? " (short)" : ""}` : ""}
            </div>
            <div className="mt-1 text-[13px] text-[#0a0c0f]">{descriptionNow || <span className="text-[#7a838c]">none found in the crawl</span>}</div>
          </div>

          <div className="space-y-3 rounded-xl border border-[#ececec] bg-white p-4">
            <div>
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">Snippet rewrite drafts</div>
              <h3 className="mt-0.5 font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">Title tag &amp; meta description options</h3>
              <p className="mt-1 text-xs text-[#4a5560]">
                The model reads the searches below, the page&apos;s own words, how this site&apos;s titles are written, and any client tone &amp; style notes, then offers three title options and three meta description options. It is a draft: nothing is sent anywhere and it uses no page allowance.
              </p>
            </div>
            {d.model_ready ? (
              <div className="flex flex-wrap items-end gap-2.5">
                <label className="text-xs font-semibold text-[#171a22]">
                  How deep
                  <select value={depth} onChange={(e) => setDepth(e.target.value as CtrDepth)} className="mt-1 block rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-sm font-normal text-[#171a22]">
                    {(Object.keys(DEPTH) as CtrDepth[]).map((k) => <option key={k} value={k}>{DEPTH[k]}</option>)}
                  </select>
                </label>
                <button type="button" onClick={write} disabled={pending || running} className="cursor-pointer rounded-full bg-[#223540] px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-[#00a99d] disabled:opacity-50">
                  {pending || running ? <><Spinner />Writing…</> : draft?.status === "done" ? "Write again" : "Write title & meta options"}
                </button>
              </div>
            ) : <p className="rounded-[10px] border border-[oklch(0.88_0.08_85)] bg-[oklch(0.97_0.045_85)] p-2.5 text-xs text-[oklch(0.42_0.1_65)]">The model needs the Anthropic key on the API service.</p>}
            {draft?.status === "failed" ? <p role="alert" className="text-xs font-semibold text-[oklch(0.48_0.17_25)]">{draft.error}</p> : null}
            {draft?.status === "done" && draft.options ? (
              <div className="space-y-4 pt-1">
                {draft.diagnosis ? (
                  <p className="rounded-[10px] border border-[#ececec] bg-[#f8f8f8] px-3 py-2 text-xs text-[#171a22]">
                    <strong>Why the snippet earns less:</strong> {draft.diagnosis}
                  </p>
                ) : null}
                {draft.page_read === false ? <p className="text-xs text-[oklch(0.42_0.1_65)]">The page itself could not be read, so these come from its title, description and searches only.</p> : null}

                <div>
                  <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                    Title tag options (target ≤ 60 chars)
                  </div>
                  <ol className="space-y-2">
                    {draft.options.map((o, i) => (
                      <li key={i} className="rounded-[10px] border border-[#ececec] bg-[#f8f8f8] p-3">
                        <div className="flex flex-wrap items-start gap-2">
                          <div className="min-w-0 flex-1 font-semibold text-[#0a0c0f]">{o.title}</div>
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ${o.too_long ? "bg-[oklch(0.97_0.045_85)] text-[oklch(0.42_0.1_65)]" : "bg-[#f1f3f4] text-[#4a5560]"}`}>
                            {o.length}/60 chars{o.too_long ? " · may be cut off" : ""}
                          </span>
                          <button type="button" onClick={() => copy(`title-${i}`, o.title)} className="cursor-pointer rounded-full border border-[#e3e6e8] bg-white px-3 py-0.5 text-xs font-semibold text-[#223540] hover:border-[#00a99d]">
                            {copied === `title-${i}` ? "Copied ✓" : "Copy"}
                          </button>
                        </div>
                        {draft.recommended === i ? <span className="mt-1.5 inline-block rounded-full bg-[#e6f7f5] px-2.5 py-0.5 text-[11px] font-semibold text-[#00665f]">Start with this one</span> : null}
                        <p className="mt-1 text-xs text-[#4a5560]">{o.why}</p>
                        {o.serves.length > 0 ? <p className="mt-0.5 text-xs text-[#7a838c]">Serves: {o.serves.join(", ")}</p> : null}
                      </li>
                    ))}
                  </ol>
                </div>

                <div>
                  <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                    Meta description options (target ≤ 160 chars)
                  </div>
                  {draft.descriptions && draft.descriptions.length > 0 ? (
                    <ol className="space-y-2">
                      {draft.descriptions.map((o, i) => (
                        <li key={i} className="rounded-[10px] border border-[#ececec] bg-[#f8f8f8] p-3">
                          <div className="flex flex-wrap items-start gap-2">
                            <div className="min-w-0 flex-1 text-[13px] font-medium text-[#0a0c0f]">{o.description}</div>
                            <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ${o.too_long ? "bg-[oklch(0.97_0.045_85)] text-[oklch(0.42_0.1_65)]" : "bg-[#e6f7f5] text-[#00665f]"}`}>
                              {o.length}/160 chars{o.too_long ? " · over 160-char target" : " · fits"}
                            </span>
                            <button type="button" onClick={() => copy(`desc-${i}`, o.description)} className="cursor-pointer rounded-full border border-[#e3e6e8] bg-white px-3 py-0.5 text-xs font-semibold text-[#223540] hover:border-[#00a99d]">
                              {copied === `desc-${i}` ? "Copied ✓" : "Copy"}
                            </button>
                          </div>
                          {draft.recommended_description === i ? <span className="mt-1.5 inline-block rounded-full bg-[#e9fedc] px-2.5 py-0.5 text-[11px] font-semibold text-[#2f5a00]">Start with this one</span> : null}
                          <p className="mt-1 text-xs text-[#4a5560]">{o.why}</p>
                          {o.serves.length > 0 ? <p className="mt-0.5 text-xs text-[#7a838c]">Serves: {o.serves.join(", ")}</p> : null}
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="rounded-[10px] border border-dashed border-[#d3d7d9] bg-[#f8f8f8] px-3 py-2.5 text-xs text-[#7a838c]">
                      No meta description options were saved on this earlier draft. Click &ldquo;Write again&rdquo; to generate title and meta description rewrites together.
                    </p>
                  )}
                </div>

                <p className="text-xs text-[#7a838c]">{DEPTH[draft.depth]} · ${draft.cost_usd.toFixed(2)} · read {draft.searches_used} searches. Check each against the page before using it. After you change the title or description, add a note to the change log so the 28-day check below measures it.</p>
              </div>
            ) : null}
          </div>

          <div>
            <h3 className="font-bold">What it ranks for</h3>
            <p className="text-xs text-[var(--text-tertiary)]">{d.searches_total > d.searches.length ? `The ${d.searches.length} with the most clicks to gain, of ${d.searches_total}. ` : ""}Clean means the search is not worth fixing: it is near the benchmark, or too few clicks are at stake. Brand searches are left out.</p>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-xs">
                <thead><tr><th className={th}>Search</th><th className={th}>Pos.</th><th className={th}>Impr.</th><th className={th}>CTR</th><th className={th}>Expected</th><th className={th}>Clicks to gain</th><th className={th}>Bing</th></tr></thead>
                <tbody>
                  {d.searches.map((s) => (
                    <tr key={s.query} className="border-t border-[var(--border)]">
                      <td className="px-3 py-2 font-medium">{s.query}</td>
                      <td className={td}>{s.position}</td>
                      <td className={td}>{num(s.impressions)}</td>
                      <td className={td}>{s.ctr}%</td>
                      <td className={td}>{s.expected_ctr}%</td>
                      <td className={`${td} font-semibold ${s.below ? "text-red-700" : "text-green-700"}`}>{s.below ? `+${s.extra_clicks}` : "Clean"}</td>
                      <td className={td}>{s.bing ? `${s.bing.clicks} of ${num(s.bing.impressions)}${s.bing.position ? ` · pos ${s.bing.position}` : ""}` : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <h3 className="font-bold">Changes to this page</h3>
            {d.changes.length === 0 ? (
              <p className="text-xs text-[var(--text-secondary)]">No shipped task or change-log note is recorded for this page. When you change the title or description, add a note in OrganicIQ insights&apos;s change log, and the before and after click-through appears here.</p>
            ) : (
              <ul className="mt-2 space-y-2 text-xs">
                {d.changes.map((c, i) => (
                  <li key={i} className="rounded-lg border border-[var(--border)] p-2">
                    <div><span className="font-semibold">{day(c.date)}</span> · {c.kind}: {c.text}</div>
                    <div className="mt-1 text-[var(--text-secondary)]">28 days before: <Window w={c.before} /></div>
                    <div className="text-[var(--text-secondary)]">28 days after: {c.measured_on ? <span className="text-[var(--text-tertiary)]">measured on {day(c.measured_on)}</span> : <Window w={c.after} />}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

function PageRow({ p, onOpen }: { p: CtrPage; onOpen: (url: string) => void }) {
  return (
    <tr className="cursor-pointer border-t border-[var(--border)] align-top hover:bg-[var(--bg)]" onClick={() => onOpen(p.url)}>
      <td className="max-w-md px-3 py-2">
        <div className="break-all font-semibold">{shortPage(p.url)}</div>
        <div className="truncate text-xs text-[var(--text-tertiary)]" title={p.title ?? undefined}>{p.title ?? "no title found"}</div>
      </td>
      <td className={td}>{p.position}</td>
      <td className={td}>{num(p.impressions)}</td>
      <td className={td}>{p.ctr}%</td>
      <td className={td}>{num(p.clicks)} <span className="text-xs text-[var(--text-tertiary)]">of {num(p.expected_clicks)}</span></td>
      <td className={`${td} font-semibold ${p.below ? "text-red-700" : "text-green-700"}`}>{p.below ? `+${num(Math.round(p.extra_clicks))}` : "Clean"}</td>
      <td className="px-3 py-2 text-xs text-[var(--text-secondary)]">{p.below ? `${p.searches_below} search${p.searches_below === 1 ? "" : "es"} below` : ""}</td>
    </tr>
  );
}

export function CtrOptimizer({ client, from, to, q, data, error }: { client: Client; from: string; to: string; q: string; data: Ctr | null; error: string | null }) {
  const router = useRouter();
  const [custom, setCustom] = useState({ from, to });
  const [filter, setFilter] = useState<"below" | "all">("below");
  const [open, setOpen] = useState<string | null>(useSearchParams().get("page"));
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const [search, setSearch] = useState(q);
  const go = (f: string, t: string, query = q) => {
    const params = new URLSearchParams({ from: f, to: t });
    if (query) params.set("q", query);
    router.push(`/${client.slug}/ctr?${params}`);
  };
  const ranges = presets();
  const active = ranges.find((r) => r.from === from && r.to === to)?.key ?? "custom";
  const pages = data ? (filter === "below" && !q ? data.pages.filter((p) => p.below) : data.pages) : [];
  const searches: CtrSearch[] = data?.searches.slice(0, 15) ?? [];

  return (
    <section className="max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">CTR optimizer</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Pages and searches that earn fewer clicks than their position should, ranked by the clicks available. The fix is a better title and description.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-2 text-sm">
        {ranges.map((r) => (
          <button key={r.key} type="button" onClick={() => go(r.from, r.to)} className={`rounded-lg border px-3 py-1.5 font-semibold ${active === r.key ? "border-[var(--brand-teal)] bg-[var(--brand-teal)] text-white" : "border-[var(--border)] bg-white"}`}>{r.label}</button>
        ))}
        <label className="text-xs font-semibold">From<input type="date" value={custom.from} onChange={(e) => setCustom({ ...custom, from: e.target.value })} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-1.5 text-sm" /></label>
        <label className="text-xs font-semibold">To<input type="date" value={custom.to} onChange={(e) => setCustom({ ...custom, to: e.target.value })} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-1.5 text-sm" /></label>
        <button type="button" onClick={() => go(custom.from, custom.to)} disabled={!custom.from || !custom.to || custom.to < custom.from} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 font-semibold disabled:opacity-50">Apply</button>
        <span className="pb-2 text-xs text-[var(--text-tertiary)]">{day(from)} to {day(to)}</span>
      </div>

      <form
        className="flex flex-wrap items-center gap-2 text-sm"
        onSubmit={(e) => {
          e.preventDefault();
          go(from, to, search.trim());
        }}
        role="search"
      >
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Find a page: part of its address, its title, or a search it ranks for"
          aria-label="Find a page"
          className="min-w-[20rem] flex-1 rounded-lg border border-[var(--border)] bg-white px-3 py-2"
        />
        <button type="submit" className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 font-semibold">Find</button>
        {q ? <button type="button" onClick={() => { setSearch(""); go(from, to, ""); }} className="text-xs font-semibold underline">Clear</button> : null}
      </form>

      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}

      {data && data.coverage.days < 0.5 * ((new Date(`${to}T00:00:00`).getTime() - new Date(`${from}T00:00:00`).getTime()) / 86400000 + 1) ? (
        <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          Search Console holds searches for only {data.coverage.days} day{data.coverage.days === 1 ? "" : "s"} of this range{data.coverage.first ? ` (${day(data.coverage.first)} to ${day(data.coverage.last ?? data.coverage.first)})` : ""}, so these numbers are partial. Pull Search Console again on the Connections page to fill the rest.
        </p>
      ) : null}

      {data && data.score == null ? (
        <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">There are not enough searches in this range to judge click-through: Search Console needs at least {100} impressions on a search ranking in the top 20. Try a longer range.</p>
      ) : null}

      {data && data.score != null ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="Clickability" value={`${data.score}%`} note={`${num(data.clicks)} clicks earned for every ${num(data.expected_clicks)} the benchmark expects at these positions`} />
            <Kpi label="Clicks available" value={`+${num(data.extra_clicks)}`} note="if the pages below benchmark reached it" />
            <Kpi label="Pages below benchmark" value={num(data.pages_below)} note={`of ${num(data.pages_counted)} pages ranking in the top 20`} />
            <Kpi label="Searches below benchmark" value={num(data.searches_below)} note={`of ${num(data.searches_counted)} with enough impressions`} />
          </div>
          {data.bing ? <p className="-mt-3 text-xs text-[var(--text-secondary)]">Bing: {data.bing.score}% of benchmark, {num(data.bing.clicks)} clicks against {num(data.bing.expected_clicks)} expected, across {data.bing.searches} searches. Bing reports by search only, so it is shown here and on each page&apos;s searches, not ranked by page.</p> : null}

          <section className={`${card} p-5`}>
            <h2 className="text-lg font-bold">Clickability by month</h2>
            <p className="text-xs text-[var(--text-tertiary)]">Clicks earned per 100 the benchmark expects, for the twelve months ending with this range. Higher is better.</p>
            <div className="mt-2">
              <WeeklyLine label="Clickability by month" periodLabel="Month of" spanDays={28} format={(n) => `${n}%`} points={data.monthly.map((m) => ({ week: `${m.month}-01`, value: m.score }))} />
            </div>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">{data.monthly.filter((m) => m.score != null).length > 0 ? `Best month: ${monthLabel([...data.monthly].filter((m) => m.score != null).sort((a, b) => (b.score ?? 0) - (a.score ?? 0))[0].month)}.` : ""}</p>
          </section>

          <section className={card}>
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4">
              <h2 className="text-lg font-bold">{q ? `Pages matching “${q}”` : "Pages to fix, most clicks first"}</h2>
              <div className={`flex gap-2 text-xs ${q ? "hidden" : ""}`}>
                {(["below", "all"] as const).map((k) => (
                  <button key={k} type="button" onClick={() => setFilter(k)} className={`rounded-full border px-3 py-1 font-semibold ${filter === k ? "border-[var(--brand-teal)] bg-[var(--brand-teal)] text-white" : "border-[var(--border)] bg-white"}`}>
                    {k === "below" ? `Below benchmark (${data.pages_below})` : "All pages"}
                  </button>
                ))}
              </div>
            </div>
            <p className="px-5 text-xs text-[var(--text-tertiary)]">{data.rule} Open a page to see its title, description and searches, and to have the model write title options.</p>
            <div className="overflow-x-auto">
              <table className="mt-2 w-full text-sm">
                <thead><tr><th className={th}>Page</th><th className={th}>Pos.</th><th className={th}>Impr.</th><th className={th}>CTR</th><th className={th}>Clicks</th><th className={th}>To gain</th><th className={th} /></tr></thead>
                <tbody>
                  {pages.map((p) => <PageRow key={p.url} p={p} onOpen={setOpen} />)}
                  {pages.length === 0 ? <tr><td colSpan={7} className={`px-5 py-4 font-semibold ${q ? "text-[var(--text-secondary)]" : "text-green-700"}`}>{q ? `No page with search data in this range matches “${q}”.` : "Clean: no page is below the benchmark in this range."}</td></tr> : null}
                </tbody>
              </table>
            </div>
          </section>

          {searches.length > 0 ? (
            <section className={card}>
              <h2 className="px-5 pt-4 text-lg font-bold">{q ? `Searches below benchmark matching “${q}”` : "Searches below benchmark"}</h2>
              <p className="px-5 text-xs text-[var(--text-tertiary)]">The 15 with the most clicks to gain, whichever page they land on.</p>
              <div className="overflow-x-auto">
                <table className="mt-2 w-full text-sm">
                  <thead><tr><th className={th}>Search</th><th className={th}>Page</th><th className={th}>Pos.</th><th className={th}>Impr.</th><th className={th}>CTR</th><th className={th}>Expected</th><th className={th}>To gain</th></tr></thead>
                  <tbody>
                    {searches.map((s) => (
                      <tr key={`${s.query}|${s.url}`} className="cursor-pointer border-t border-[var(--border)] hover:bg-[var(--bg)]" onClick={() => setOpen(s.url)}>
                        <td className="px-3 py-2 font-medium">{s.query}</td>
                        <td className="max-w-xs break-all px-3 py-2 text-xs text-[var(--text-secondary)]">{shortPage(s.url)}</td>
                        <td className={td}>{s.position}</td>
                        <td className={td}>{num(s.impressions)}</td>
                        <td className={td}>{s.ctr}%</td>
                        <td className={td}>{s.expected_ctr}%</td>
                        <td className={`${td} font-semibold text-red-700`}>+{s.extra_clicks}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}
        </>
      ) : null}

      <aside aria-label="Page" aria-hidden={!open} className={`fixed right-0 top-0 z-30 flex h-full w-full max-w-2xl flex-col border-l border-[var(--border)] bg-[var(--surface)] shadow-xl transition-transform duration-200 ${open ? "translate-x-0" : "pointer-events-none translate-x-full"}`}>
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3">
          <h2 className="font-bold">Page</h2>
          <button type="button" onClick={() => setOpen(null)} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1 text-sm font-semibold">Close</button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">{open ? <PagePane client={client} url={open} from={from} to={to} /> : null}</div>
      </aside>
    </section>
  );
}
