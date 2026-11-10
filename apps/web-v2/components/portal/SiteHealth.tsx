import type { SiteHealthSummary } from "@/lib/portal";

import { card } from "./BriefParts";

const tone = (n: number) => (n >= 80 ? "bg-[var(--brand-lime)]" : n >= 60 ? "bg-amber-400" : "bg-red-500");

function Bar({ label, score, note }: { label: string; score: number | null; note?: string }) {
  return (
    <div className="grid grid-cols-[minmax(0,10rem)_1fr_2.5rem] items-center gap-3 text-sm" title={note}>
      <span className="truncate">{label}</span>
      {score == null ? <span className="text-xs text-[var(--text-secondary)]">Not measured yet</span> : <div className="h-2.5 rounded-full bg-slate-100"><div className={`h-2.5 rounded-full ${tone(score)}`} style={{ width: `${score}%` }} /></div>}
      <span className="text-right tabular-nums">{score ?? ""}</span>
    </div>
  );
}

function Score({ title, hint, score, grade, change }: { title: string; hint: string; score: number; grade: string; change: number | null }) {
  return (
    <div className={`${card} border-t-4 border-t-[var(--brand-teal)] p-4`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">{title}</div>
      <div className="mt-1 flex items-baseline gap-2"><span className="text-4xl font-bold tabular-nums text-[var(--brand-navy)]">{score}</span><span className="text-sm text-[var(--text-secondary)]">/ 100</span><span className="rounded-full bg-[var(--brand-navy)] px-2 py-0.5 text-xs font-bold text-[var(--brand-lime)]">{grade}</span></div>
      <p className={`mt-1 text-xs ${change == null || change === 0 ? "text-[var(--text-secondary)]" : change > 0 ? "text-[var(--brand-teal-hover)]" : "text-red-700"}`}>{change == null ? "First month scored." : change === 0 ? "No change on last month." : `${change > 0 ? "Up" : "Down"} ${Math.abs(change)} on last month.`}</p>
      <p className="mt-2 text-xs text-[var(--text-secondary)]">{hint}</p>
    </div>
  );
}

/** Site health as the client reads it: SEO health and GEO readiness, the checks behind each, and where the scores come from. */
export function SiteHealthView({ data }: { data: SiteHealthSummary }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Score title="SEO health" hint="Is the site technically sound for search?" score={data.seo.score} grade={data.seo.grade} change={data.seo.change} />
        <Score title="GEO readiness" hint="Can AI answers read and cite the site?" score={data.geo.score} grade={data.geo.grade} change={data.geo.change} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className={`${card} space-y-2.5 p-4`}><h3 className="text-xs font-bold uppercase tracking-wide text-[var(--text-secondary)]">What makes up SEO health</h3>{data.seo.checks.map((c) => <Bar key={c.label} label={c.label} score={c.score} note={c.total ? `${c.affected} of ${c.total} pages affected` : undefined} />)}</div>
        <div className={`${card} space-y-2.5 p-4`}><h3 className="text-xs font-bold uppercase tracking-wide text-[var(--text-secondary)]">What makes up GEO readiness</h3>{data.geo.signals.map((s) => <Bar key={s.label} label={s.label} score={s.score} note={s.summary ?? undefined} />)}</div>
      </div>
      <p className="text-xs leading-5 text-[var(--text-secondary)]">
        {data.source}{data.crawl_date ? `, crawled ${data.crawl_date}` : ""}{data.pages ? `, ${data.pages.toLocaleString("en-US")} pages` : ""}.
        {data.new_issues != null && data.fixed_issues != null ? ` Since last month ${data.fixed_issues} page issue${data.fixed_issues === 1 ? "" : "s"} fixed and ${data.new_issues} new.` : ""}
        {data.hit_limit ? " The crawl stopped at its page limit, so the score covers the pages it reached." : ""}
        {data.geo.partial ? " GEO readiness counts only the signals measured so far." : ""}
      </p>
    </div>
  );
}
