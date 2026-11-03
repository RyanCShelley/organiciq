"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Client } from "@/lib/api";
import { monthLabel } from "@/lib/focus";
import type { ShCheck, ShData, ShResponse, ShSignal } from "@/lib/site-health";

const card = "rounded-xl border border-[var(--border)] bg-[var(--surface)]";
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

const tone = (score: number) => (score >= 85 ? "#0f766e" : score >= 70 ? "#b45309" : "#b91c1c");

function Ring({ score, grade }: { score: number; grade: string }) {
  const R = 44, C = 2 * Math.PI * R;
  return (
    <svg viewBox="0 0 110 110" className="h-28 w-28 shrink-0" role="img" aria-label={`Score ${score} out of 100, grade ${grade}`}>
      <circle cx="55" cy="55" r={R} fill="none" stroke="var(--border)" strokeWidth="10" />
      <circle cx="55" cy="55" r={R} fill="none" stroke={tone(score)} strokeWidth="10" strokeLinecap="round" strokeDasharray={`${(score / 100) * C} ${C}`} transform="rotate(-90 55 55)" />
      <text x="55" y="55" textAnchor="middle" fontSize="28" fontWeight="700" fill="currentColor">{score}</text>
      <text x="55" y="74" textAnchor="middle" fontSize="12" fill="var(--text-tertiary)">{grade}</text>
    </svg>
  );
}

function Change({ now, before }: { now: number; before: number | null | undefined }) {
  if (before == null) return <span className="text-xs text-[var(--text-tertiary)]">no earlier month kept</span>;
  const d = now - before;
  if (d === 0) return <span className="text-xs font-semibold text-[var(--text-secondary)]">no change from last month</span>;
  return <span className={`text-xs font-semibold ${d > 0 ? "text-green-700" : "text-red-700"}`}>{d > 0 ? "▲" : "▼"} {Math.abs(d)} <span className="font-normal text-[var(--text-secondary)]">from last month ({before})</span></span>;
}

function ScoreCard({ title, sub, score, grade, before, children }: { title: string; sub: string; score: number; grade: string; before: number | null | undefined; children?: React.ReactNode }) {
  return (
    <div className={`${card} flex flex-wrap items-center gap-5 p-5`}>
      <Ring score={score} grade={grade} />
      <div className="min-w-0 flex-1">
        <h2 className="text-lg font-bold">{title}</h2>
        <p className="text-sm text-[var(--text-secondary)]">{sub}</p>
        <div className="mt-2"><Change now={score} before={before} /></div>
        {children}
      </div>
    </div>
  );
}

function Bar({ score }: { score: number }) {
  return (
    <div className="h-2 w-full rounded-full bg-[var(--border)]" aria-hidden>
      <div className="h-2 rounded-full" style={{ width: `${score}%`, background: tone(score) }} />
    </div>
  );
}

function IssueGroup({ c }: { c: ShCheck }) {
  const [open, setOpen] = useState(false);
  const clean = c.affected === 0;
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="font-semibold">{c.label}</div>
          <div className="text-xs text-[var(--text-secondary)]">{c.detail}</div>
        </div>
        <div className="w-40"><Bar score={c.score} /></div>
        <div className="w-24 text-right text-sm tabular-nums"><span className="font-bold">{c.score}</span><span className="text-xs text-[var(--text-tertiary)]"> · {c.weight} pts</span></div>
        {!clean && c.urls.length > 0 ? (
          <button type="button" onClick={() => setOpen((v) => !v)} className="text-xs font-semibold underline">{open ? "Hide" : `Show ${c.affected} to fix`}</button>
        ) : <span className="w-16 text-right text-xs font-semibold text-green-700">{clean ? "Clean" : ""}</span>}
      </div>
      {open ? (
        <ul className="mt-2 max-h-64 space-y-0.5 overflow-y-auto rounded-lg bg-[var(--bg)] p-3 text-xs">
          {c.key === "site_files" ? c.urls.map((u) => <li key={u}>{u}</li>) : c.urls.map((u) => <li key={u} className="break-all">{shortPage(u)}</li>)}
          {c.affected > c.urls.length ? <li className="text-[var(--text-tertiary)]">and {c.affected - c.urls.length} more</li> : null}
        </ul>
      ) : null}
    </li>
  );
}

function Signal({ s }: { s: ShSignal }) {
  const [open, setOpen] = useState(false);
  const clean = s.measured && s.affected === 0;
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="font-semibold">{s.label}</div>
          <div className="text-xs text-[var(--text-secondary)]">{s.note}</div>
          {s.summary ? <div className="mt-0.5 text-xs font-medium text-[var(--text-primary)]">{s.summary}</div> : null}
        </div>
        {s.measured && s.score != null ? (
          <>
            <div className="w-40"><Bar score={s.score} /></div>
            <div className="w-24 text-right text-sm tabular-nums"><span className="font-bold">{s.score}</span><span className="text-xs text-[var(--text-tertiary)]"> · {s.weight} pts</span></div>
            {s.affected > 0 ? (
              <button type="button" onClick={() => setOpen((v) => !v)} className="text-xs font-semibold underline">{open ? "Hide" : `Show ${s.affected} to fix`}</button>
            ) : <span className="w-16 text-right text-xs font-semibold text-green-700">{clean ? "Clean" : ""}</span>}
          </>
        ) : (
          <div className="w-64 text-right text-xs text-[var(--text-tertiary)]">Not measured: needs a finished LLM visibility run ({s.weight} pts)</div>
        )}
      </div>
      {open ? (
        <ul className="mt-2 max-h-72 space-y-1.5 overflow-y-auto rounded-lg bg-[var(--bg)] p-3 text-xs">
          {s.items.map((i, k) => (
            <li key={k}>
              {i.url ? <span className="mr-2 break-all font-semibold">{shortPage(i.url)}</span> : null}
              <span className="text-[var(--text-secondary)]">{i.text}</span>
            </li>
          ))}
          {s.affected > s.items.length ? <li className="text-[var(--text-tertiary)]">and {s.affected - s.items.length} more</li> : null}
        </ul>
      ) : null}
    </li>
  );
}

function View({ client, data }: { client: Client; data: ShData }) {
  const issues = [...data.seo.checks].sort((a, b) => b.affected - a.affected);
  return (
    <>
      {data.crawl.hit_limit ? (
        <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          The crawl stopped at its {data.crawl.limit}-page limit ({data.crawl.pages} pages), so these scores describe the pages it reached, not necessarily the whole site.
        </p>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <ScoreCard title="SEO health" sub="Is the site technically sound for search?" score={data.seo.score} grade={data.seo.grade} before={data.previous?.seo} />
        <ScoreCard title="GEO readiness" sub="Is the site ready to be read and cited by AI answers?" score={data.geo.score} grade={data.geo.grade} before={data.previous?.geo}>
          {data.geo.partial ? <p className="mt-2 text-xs text-amber-800">Scored on the signals that could be measured. Run LLM visibility to measure the rest.</p> : null}
        </ScoreCard>
      </div>

      <section className={card}>
        <h2 className="px-5 pt-4 text-lg font-bold">What to fix, most pages first</h2>
        <p className="px-5 text-xs text-[var(--text-tertiary)]">Each line is one kind of problem. The score is how much of the site it leaves clean; the points are how much that kind counts toward SEO health.</p>
        <ul className="divide-y divide-[var(--border)] px-5 pb-2">{issues.map((c) => <IssueGroup key={c.key} c={c} />)}</ul>
      </section>

      <section className={card}>
        <h2 className="px-5 pt-4 text-lg font-bold">GEO readiness, signal by signal</h2>
        <p className="px-5 text-xs text-[var(--text-tertiary)]">The same signals and weights as the GEO Grader. Open any line to see the pages or prompts to fix. Read from every crawled page and from the latest AI answers{data.geo.answers ? ` (${data.geo.answers.answers} answers, run on ${day(data.geo.answers.run_date)})` : ""}.</p>
        <ul className="divide-y divide-[var(--border)] px-5 pb-2">{data.geo.signals.map((s) => <Signal key={s.key} s={s} />)}</ul>
      </section>

      <section className={`${card} p-5`}>
        <h2 className="text-lg font-bold">New and fixed since last month</h2>
        {data.previous == null ? (
          <p className="mt-2 text-sm text-[var(--text-secondary)]">There is no earlier month to compare with yet. A month&apos;s scores are kept when its last crawl runs, so next month will show what changed.</p>
        ) : data.changes.length === 0 ? (
          <p className="mt-2 text-sm text-[var(--text-secondary)]">Nothing changed in the pages listed under each problem since {monthLabel(data.previous.month)}.</p>
        ) : (
          <ul className="mt-3 space-y-3 text-sm">
            {data.changes.map((c) => (
              <li key={c.key}>
                <div className="font-semibold">{c.label}</div>
                <div className="text-xs text-[var(--text-secondary)]">
                  {c.new_count > 0 ? <span className="font-semibold text-red-700">{c.new_count} new</span> : null}
                  {c.new_count > 0 && c.fixed_count > 0 ? " · " : ""}
                  {c.fixed_count > 0 ? <span className="font-semibold text-green-700">{c.fixed_count} fixed</span> : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
      <p className="text-xs text-[var(--text-tertiary)]">
        Worked out from the site crawl of {day(data.crawl_date)} ({data.crawl.pages} pages). <Link href={`/${client.slug}/settings/connections`} className="underline">Crawl settings</Link>
      </p>
    </>
  );
}

export function SiteHealth({ client, result, error }: { client: Client; result: ShResponse | null; error: string | null }) {
  const router = useRouter();
  const data = result?.data ?? null;
  return (
    <section className="max-w-6xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Site health</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">Two scores from the site crawl: how sound the site is for search, and how ready it is for AI answers. Each month&apos;s scores are kept.</p>
        </div>
        {result && result.months.length > 0 ? (
          <label className="text-xs font-semibold">
            Month
            <select value={result.month ?? ""} onChange={(e) => router.push(`/${client.slug}/site-health?month=${e.target.value}`)} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-1.5 text-sm font-normal">
              {result.months.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
            </select>
          </label>
        ) : null}
      </header>
      {data ? (
        <p className="-mt-3 text-xs text-[var(--text-secondary)]">
          {data.locked ? `Locked: the month is over, and this is its last crawl (${day(data.crawl_date)}).` : `This month is still running, so these scores follow each new crawl (latest ${day(data.crawl_date)}) until the month ends.`}
        </p>
      ) : null}
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      {!error && !data ? (
        <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">This site has not been crawled yet, so there is nothing to score. Pull data on the Connections page starts a crawl.</p>
      ) : null}
      {data ? <View client={client} data={data} /> : null}
    </section>
  );
}
