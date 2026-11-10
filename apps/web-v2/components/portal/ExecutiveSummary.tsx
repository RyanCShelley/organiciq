import type { ExecCompetitor, ExecData, ExecReport, ExecTopic } from "@/lib/portal";

import { card } from "./BriefParts";

const monthShort = (m: string) => new Date(`${m}-01T00:00:00`).toLocaleDateString("en-US", { month: "short" });
const monthLong = (m: string) => new Date(`${m}-01T00:00:00`).toLocaleDateString("en-US", { month: "long", year: "numeric" });
const num = (v: number | null | undefined) => (v == null ? "No data" : Math.round(v).toLocaleString("en-US"));

const HEAT = {
  green: "bg-[var(--brand-lime-soft)] text-[var(--brand-navy)]",
  amber: "bg-amber-100 text-amber-900",
  red: "bg-red-100 text-red-800",
  none: "bg-slate-100 text-[var(--text-secondary)]",
} as const;
const TONE = { good: "text-[var(--brand-teal-hover)]", bad: "text-red-700", neutral: "text-[var(--text-secondary)]" } as const;

function Chip({ heat, children }: { heat: keyof typeof HEAT | null; children: React.ReactNode }) {
  return <span className={`inline-block min-w-14 rounded-full px-2.5 py-1 text-center text-xs font-bold tabular-nums ${HEAT[heat ?? "none"]}`}>{children}</span>;
}

function Note({ text }: { text?: string }) {
  return text ? <p className="mt-3 border-l-4 border-[var(--brand-teal)] pl-4 text-sm italic leading-6 text-[var(--text-secondary)]">{text}</p> : null;
}

function H({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div className="mb-3">
      <h2 className="text-lg font-bold text-[var(--brand-navy)]">{children}</h2>
      {sub ? <p className="mt-0.5 text-sm text-[var(--text-secondary)]">{sub}</p> : null}
    </div>
  );
}

function ClicksByMonth({ d }: { d: ExecData }) {
  const max = Math.max(1, ...d.clicks_by_month.map((m) => m.value ?? 0));
  return (
    <div className={`${card} p-5`}>
      <div className="flex h-44 items-end gap-1.5" role="img" aria-label="Google clicks by month">
        {d.clicks_by_month.map((m) => {
          const isNow = m.month === d.month, isYa = m.month === d.clicks_year_ago_month;
          return (
            <div key={m.month} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1">
              <span className={`text-[10px] tabular-nums ${isNow || isYa ? "font-bold text-[var(--brand-navy)]" : "text-[var(--text-secondary)]"}`}>{m.value == null ? "" : num(m.value)}</span>
              <div className={`w-full rounded-t ${isNow ? "bg-[var(--brand-teal)]" : isYa ? "bg-[var(--brand-lime)]" : "bg-[var(--brand-teal-soft)]"}`} style={{ height: `${Math.max(2, ((m.value ?? 0) / max) * 100)}%` }} />
              <span className="text-[10px] text-[var(--text-secondary)]">{monthShort(m.month)}</span>
            </div>
          );
        })}
      </div>
      <p className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-[var(--text-secondary)]">
        <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm bg-[var(--brand-teal)]" />{monthLong(d.month)}</span>
        <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm bg-[var(--brand-lime)]" />Same month last year</span>
      </p>
    </div>
  );
}

function Competitors({ rows, brand }: { rows: ExecCompetitor[]; brand: string }) {
  const max = Math.max(1, ...rows.map((r) => r.visibility));
  return (
    <div className={`${card} overflow-x-auto`}>
      <table className="w-full min-w-[34rem] text-sm">
        <thead><tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-wide text-[var(--text-secondary)]"><th className="px-4 py-3">Site</th><th className="px-4 py-3">Google visibility</th><th className="px-4 py-3 text-right">3-month change</th><th className="px-4 py-3 text-right">AI share of voice</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name} className={`border-b border-[var(--border)] last:border-0 ${r.is_self ? "bg-[var(--brand-teal-soft)]/50 font-semibold" : ""}`}>
              <td className="px-4 py-3">{r.is_self ? brand : r.name}{r.is_self ? <span className="ml-2 text-xs font-bold text-[var(--brand-teal-hover)]">You</span> : null}</td>
              <td className="px-4 py-3"><div className="flex items-center gap-3"><div className="h-2 w-28 rounded-full bg-slate-100"><div className={`h-2 rounded-full ${r.is_self ? "bg-[var(--brand-teal)]" : "bg-[var(--brand-navy-line)]"}`} style={{ width: `${(r.visibility / max) * 100}%` }} /></div><span className="tabular-nums">{r.visibility.toFixed(1)}%</span></div></td>
              <td className={`px-4 py-3 text-right tabular-nums ${r.change_pct == null ? "text-[var(--text-secondary)]" : r.change_pct >= 0 ? TONE.good : TONE.bad}`}>{r.change_pct == null ? "Not tracked" : `${r.change_pct > 0 ? "+" : ""}${r.change_pct.toFixed(0)}%`}</td>
              <td className="px-4 py-3 text-right tabular-nums">{r.ai_share_pct == null ? "Not named" : `${Math.round(r.ai_share_pct)}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Topics({ rows }: { rows: ExecTopic[] }) {
  return (
    <div className={`${card} overflow-x-auto`}>
      <table className="w-full min-w-[52rem] text-sm">
        <thead><tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-wide text-[var(--text-secondary)]"><th className="px-4 py-3">Topic</th><th className="px-3 py-3 text-center">Google top-10 share of demand</th><th className="px-3 py-3 text-center">AI share of voice</th><th className="px-3 py-3">AI leader</th><th className="px-3 py-3 text-right">Non-brand clicks vs last year</th><th className="px-4 py-3">Read-out</th></tr></thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.name} className="border-b border-[var(--border)] align-top last:border-0">
              <td className="px-4 py-3"><div className="font-semibold">{t.name}</div><div className="text-xs text-[var(--text-secondary)]">{t.keywords} keywords{t.searches_per_month ? ` · ${num(t.searches_per_month)} searches a month` : ""}</div></td>
              <td className="px-3 py-3 text-center">{t.google_top10_pct == null ? <Chip heat={null}>-</Chip> : <Chip heat={t.google_heat}>{Math.round(t.google_top10_pct)}%</Chip>}</td>
              <td className="px-3 py-3 text-center">{t.ai_share_pct == null ? <Chip heat={null}>-</Chip> : <Chip heat={t.ai_heat}>{Math.round(t.ai_share_pct)}%</Chip>}</td>
              <td className="px-3 py-3 text-xs">{t.ai_leader ? <><span className="font-semibold">{t.ai_leader.is_self ? "You" : t.ai_leader.name}</span> <span className="text-[var(--text-secondary)]">{Math.round(t.ai_leader.share_pct)}%</span></> : "-"}</td>
              <td className="px-3 py-3 text-right text-xs tabular-nums">{t.clicks.value == null ? <span className="text-[var(--text-secondary)]">No data</span> : <><span className="font-semibold">{num(t.clicks.value)}</span> <span className={t.clicks.change == null ? "" : t.clicks.change >= 0 ? TONE.good : TONE.bad}>{t.clicks.change == null ? "" : `(${t.clicks.change > 0 ? "+" : ""}${num(t.clicks.change)})`}</span></>}</td>
              <td className="px-4 py-3 text-xs leading-5">{t.read_out}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-[var(--border)] px-4 py-3 text-xs text-[var(--text-secondary)]">
        <span className="mr-3"><Chip heat="green">High</Chip> strong</span><span className="mr-3"><Chip heat="amber">Mid</Chip> present</span><span><Chip heat="red">Low</Chip> a gap</span>
      </p>
    </div>
  );
}

/** The leadership page: headline figures, the short version, clicks by month, visibility by topic and against peers, share of voice, priorities and the sources. */
export function ExecutiveSummary({ report }: { report: ExecReport }) {
  const d = report.data;
  const lists = [
    { key: "going_well", title: "Going well", cls: "bg-[var(--brand-lime-soft)] border-[var(--brand-lime)]" },
    { key: "to_watch", title: "To watch", cls: "bg-amber-50 border-amber-200" },
    { key: "gaps", title: "Biggest gaps", cls: "bg-red-50 border-red-200" },
  ] as const;
  const shown = lists.filter((l) => (report.highlights?.[l.key] ?? []).length);
  const n = report.notes ?? {};
  return (
    <div className="space-y-12">
      <header className="rounded-2xl bg-[var(--brand-navy)] p-7 text-white">
        <p className="text-xs font-bold uppercase tracking-widest text-[var(--brand-lime)]">Executive summary · {monthLong(d.month)}</p>
        <h1 className="mt-2 text-2xl font-bold leading-tight sm:text-3xl">{report.title || `${d.brand} search and AI visibility`}</h1>
        {report.analysis ? <p className="mt-3 max-w-2xl whitespace-pre-line text-sm leading-6 text-white/80">{report.analysis}</p> : null}
        <p className="mt-4 text-xs text-white/60">Prepared by your consultant · published {report.published_at?.slice(0, 10)}</p>
      </header>

      <section aria-label="Headline figures" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {d.kpis.map((k) => (
          <div key={k.label} className={`${card} border-t-4 border-t-[var(--brand-teal)] p-4`}>
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">{k.label}</div>
            <div className={`mt-1 text-3xl font-bold tabular-nums ${k.value == null ? "text-[var(--text-secondary)]" : "text-[var(--brand-navy)]"}`}>{k.value == null ? "No data" : typeof k.value === "number" ? `${k.unit === "%" ? k.value.toFixed(k.value % 1 ? 1 : 0) : num(k.value)}${k.unit}` : k.value}</div>
            <p className={`mt-1 text-xs leading-5 ${TONE[k.tone]}`}>{k.sub}</p>
          </div>
        ))}
      </section>

      {shown.length ? (
        <section>
          <H>The short version</H>
          <div className={`grid gap-4 ${shown.length === 1 ? "" : shown.length === 2 ? "sm:grid-cols-2" : "lg:grid-cols-3"}`}>
            {shown.map((l) => (
              <div key={l.key} className={`rounded-2xl border p-5 ${l.cls}`}>
                <h3 className="text-xs font-bold uppercase tracking-wide text-[var(--brand-navy)]">{l.title}</h3>
                <ul className="mt-3 space-y-3 text-sm leading-6">{report.highlights[l.key].map((p, i) => <li key={i} className="flex gap-2"><span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--brand-navy)] opacity-50" /><span>{p}</span></li>)}</ul>
              </div>
            ))}
          </div>
          <Note text={n.short_version} />
        </section>
      ) : null}

      <section>
        <H sub="Google clicks each month, with the same month last year picked out.">Clicks from Google</H>
        <ClicksByMonth d={d} />
        <Note text={n.clicks} />
      </section>

      {d.topics.length ? (
        <section>
          <H sub="How each tracked topic does in Google and in AI answers.">Visibility by topic</H>
          <Topics rows={d.topics} />
          <Note text={n.topics} />
        </section>
      ) : null}

      {d.competitors.length ? (
        <section>
          <H sub="Organic IQ's SE Ranking data. Competitors show their latest level only.">Against competitors</H>
          <Competitors rows={d.competitors} brand={d.brand} />
          <Note text={n.competitors} />
        </section>
      ) : null}

      {d.ai_vendors.length ? (
        <section>
          <H sub={`How often each vendor is named in AI answers, from ${d.ai_runs} check${d.ai_runs === 1 ? "" : "s"}.`}>AI share of voice</H>
          <div className={`${card} space-y-2.5 p-5`}>
            {d.ai_vendors.map((v) => (
              <div key={v.name} className="grid grid-cols-[8rem_1fr_3rem] items-center gap-3 text-sm">
                <span className={`truncate ${v.is_self ? "font-bold" : ""}`}>{v.name}{v.is_self ? " (you)" : ""}</span>
                <div className="h-3 rounded-full bg-slate-100"><div className={`h-3 rounded-full ${v.is_self ? "bg-[var(--brand-teal)]" : "bg-[var(--brand-navy-line)]"}`} style={{ width: `${Math.min(100, v.share_pct)}%` }} /></div>
                <span className="text-right tabular-nums">{Math.round(v.share_pct)}%</span>
              </div>
            ))}
          </div>
          <Note text={n.share_of_voice} />
        </section>
      ) : null}

      {d.priorities.length ? (
        <section>
          <H sub="From the action plan.">Priorities for the next quarter</H>
          <ol className="space-y-3">
            {d.priorities.map((p, i) => (
              <li key={i} className={`${card} flex gap-4 p-4`}>
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[var(--brand-navy)] text-sm font-bold text-[var(--brand-lime)]">{i + 1}</span>
                <div><div className="font-semibold">{p.title}</div><p className="mt-0.5 text-sm leading-6 text-[var(--text-secondary)]">{p.action}</p></div>
              </li>
            ))}
          </ol>
          <Note text={n.priorities} />
        </section>
      ) : null}

      <section>
        <H>About the data</H>
        <ul className="space-y-2 text-xs leading-5 text-[var(--text-secondary)]">{d.about.map((a, i) => <li key={i}>{a}</li>)}</ul>
        <p className="mt-3 text-xs text-[var(--text-secondary)]">Sources: {d.sources.join(", ")}. Prepared with Organic IQ.</p>
      </section>
    </div>
  );
}
