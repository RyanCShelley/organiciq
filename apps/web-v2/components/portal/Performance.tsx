import type { ReactNode } from "react";

import type { OutcomeCard, Performance, ReportData } from "@/lib/portal";

const monthName = (m: string, long = false) => new Date(`${m}-01T00:00:00`).toLocaleDateString("en-US", { month: long ? "long" : "short", ...(long ? { year: "numeric" } : {}) });
const num = (v: number | null | undefined, d = 0) => (v == null ? "–" : v.toLocaleString("en-US", { maximumFractionDigits: d }));

/** ▲ 5% in green, ▼ 29% in red; for a measure where lower is better the colours swap. No change says "flat", no figure says so. */
function Delta({ pct, lower = false, none = "no figure" }: { pct: number | null | undefined; lower?: boolean; none?: string }) {
  if (pct == null) return <span className="text-[var(--text-tertiary)]">{none}</span>;
  if (Math.abs(pct) < 1) return <span className="text-[var(--text-secondary)]">flat</span>;
  const good = lower ? pct < 0 : pct > 0;
  return <span className={`font-medium ${good ? "text-green-700" : "text-red-700"}`}>{pct > 0 ? "▲" : "▼"} {Math.abs(Math.round(pct))}%</span>;
}

/** A small line through the months. Fewer than two points draws nothing: no line from too little. */
function Run({ points, good }: { points: { month: string; value: number | null }[]; good: boolean }) {
  const have = points.filter((p) => p.value != null) as { month: string; value: number }[];
  if (have.length < 2) return <p className="mt-3 text-xs text-[var(--text-tertiary)]">Fewer than three months of data.</p>;
  const lo = Math.min(...have.map((p) => p.value));
  const hi = Math.max(...have.map((p) => p.value));
  const y = (v: number) => (hi === lo ? 11 : 20 - ((v - lo) / (hi - lo)) * 18);
  const x = (i: number) => 2 + (i / (points.length - 1)) * 116;
  const path = points.map((p, i) => (p.value == null ? null : `${x(i)},${y(p.value)}`)).filter(Boolean).join(" ");
  return (
    <div className="mt-3">
      <svg width="100%" height="24" viewBox="0 0 120 24" preserveAspectRatio="none" aria-hidden><polyline points={path} fill="none" stroke={good ? "#3b6d11" : "#a32d2d"} strokeWidth="2" /></svg>
      <p className="text-xs text-[var(--text-tertiary)]">{points.map((p) => `${monthName(p.month)} ${num(p.value)}`).join(" · ")}</p>
    </div>
  );
}

function Section({ title, sentence, children }: { title: string; sentence?: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <div><h2 className="text-xl font-bold">{title}</h2>{sentence ? <p className="mt-1 text-sm text-[var(--text-secondary)]">{sentence}</p> : null}</div>
      {children}
    </section>
  );
}

const th = "py-2 text-xs font-medium text-[var(--text-tertiary)]";

export function PerformanceView({ data }: { data: ReportData }) {
  const p = data.performance!;
  const { conversions, visibility, traffic } = p.outcomes;
  const cards = [conversions, visibility, traffic].filter(Boolean) as OutcomeCard[];
  return (
    <div className="mx-auto max-w-3xl space-y-12">
      <header className="space-y-2">
        <p className="text-xs font-medium tracking-wide text-[var(--text-tertiary)]">SMA MARKETING · MONTHLY PERFORMANCE REPORT</p>
        <p className="text-sm text-[var(--text-secondary)]">{p.site} · {monthName(p.month, true)} compared with {monthName(p.previous_month, true)} and {monthName(p.last_year, true)} · Sources: {p.sources.join(", ")}</p>
      </header>

      <Section title="The three outcomes" sentence="Are we being found, who is coming, and is it turning into business.">
        {cards.length ? (
          <div className="grid gap-4 sm:grid-cols-3">
            {cards.map((c) => {
              const rising = (c.vs_previous.change_pct ?? 0) >= 0;
              return (
                <div key={c.label} className="rounded-2xl border border-[var(--border)] bg-white p-5">
                  <div className="text-sm text-[var(--text-secondary)]">{c.label}</div>
                  <div className="mt-1 text-4xl font-bold tabular-nums">{num(c.value)}</div>
                  <div className="mb-4 text-sm text-[var(--text-secondary)]">{c.caption}</div>
                  <dl className="space-y-1 text-sm">
                    <div className="flex justify-between gap-2"><dt className="text-[var(--text-secondary)]">vs {monthName(p.previous_month)}</dt><dd><Delta pct={c.vs_previous.change_pct} lower={c.lower_is_better} none={c.vs_previous.value != null ? `was ${num(c.vs_previous.value)}` : "no figure"} /></dd></div>
                    <div className="flex justify-between gap-2"><dt className="text-[var(--text-secondary)]">vs {monthName(p.last_year, true)}</dt><dd><Delta pct={c.vs_last_year.change_pct} lower={c.lower_is_better} none={c.vs_last_year.value != null ? `was ${num(c.vs_last_year.value)}` : "no data then"} /></dd></div>
                  </dl>
                  <Run points={c.run} good={c.lower_is_better ? !rising : rising} />
                </div>
              );
            })}
          </div>
        ) : <p className="text-sm text-[var(--text-secondary)]">Nothing is connected yet to measure the three outcomes for this month.</p>}
      </Section>

      {p.key_actions.has_definitions ? (
        <Section title="Conversions" sentence="Key actions are the Google Analytics events we count as business results.">
          <table className="w-full text-sm">
            <thead><tr className="text-right"><th className={`${th} text-left`}>Key action</th><th className={th}>{monthName(p.month)}</th><th className={th}>{monthName(p.previous_month)}</th><th className={th}>Change</th></tr></thead>
            <tbody className="tabular-nums">
              {p.key_actions.rows.map((r) => <tr key={r.label} className="border-t border-[var(--border)] text-right"><td className="py-2.5 text-left">{r.label}</td><td>{num(r.count)}</td><td>{num(r.previous)}</td><td><Delta pct={r.change_pct} none="new" /></td></tr>)}
              {p.key_actions.total ? <tr className="border-t border-[var(--border)] text-right font-semibold"><td className="py-2.5 text-left">Total key actions</td><td>{num(p.key_actions.total.count)}</td><td>{num(p.key_actions.total.previous)}</td><td><Delta pct={p.key_actions.total.change_pct} /></td></tr> : null}
            </tbody>
          </table>
        </Section>
      ) : null}

      {p.rankings.rows.length ? (
        <Section title="Google rankings" sentence={`Position at the first and last check of the month${p.rankings.checked_from && p.rankings.checked_to ? ` (${p.rankings.checked_from} and ${p.rankings.checked_to})` : ""}. A keyword not found in the top 100 shows as out.`}>
          <table className="w-full text-sm">
            <thead><tr className="text-right"><th className={`${th} text-left`}>Keyword</th><th className={th}>Searches a month</th><th className={th}>Start</th><th className={th}>End</th><th className={th}>Change</th></tr></thead>
            <tbody className="tabular-nums">
              {p.rankings.rows.map((r) => (
                <tr key={r.keyword} className="border-t border-[var(--border)] text-right">
                  <td className="py-2.5 text-left">{r.keyword}</td><td>{num(r.volume)}</td><td>{r.start == null ? "out" : `#${r.start}`}</td><td>{r.end == null ? "out" : `#${r.end}`}</td>
                  <td>{r.change == null ? <span className={r.state === "lost" ? "font-medium text-red-700" : "text-[var(--text-tertiary)]"}>{r.state === "lost" ? "▼ out" : r.state === "new" ? "new" : "–"}</span> : r.change === 0 ? <span className="text-[var(--text-secondary)]">held</span> : <span className={`font-medium ${r.change > 0 ? "text-green-700" : "text-red-700"}`}>{r.change > 0 ? "▲" : "▼"} {Math.abs(r.change)}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      {p.channels.length ? (
        <Section title="Where visitors came from" sentence="Share of all visits, and the change on last month.">
          <ul className="text-sm">
            {p.channels.map((c) => (
              <li key={c.key} className="grid grid-cols-[8rem_1fr_5rem_4rem] items-center gap-3 py-1.5">
                <span>{c.label}</span>
                <div className="h-1.5 rounded bg-[var(--border)]"><div className="h-1.5 rounded bg-[var(--brand-teal)]" style={{ width: `${Math.min(100, c.share_pct ?? 0)}%` }} /></div>
                <span className="text-right tabular-nums">{num(c.sessions)}</span>
                <span className="text-right"><Delta pct={c.change_pct} none="–" /></span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {p.landing_pages.length ? (
        <Section title="Organic search landing pages" sentence="Key actions are those attributed to the landing page; most happen later in the visit on other pages.">
          <table className="w-full text-sm">
            <thead><tr className="text-right"><th className={`${th} text-left`}>Page</th><th className={th}>{monthName(p.month)} visits</th><th className={th}>{monthName(p.previous_month)}</th><th className={th}>Key actions</th></tr></thead>
            <tbody className="tabular-nums">
              {p.landing_pages.map((r) => <tr key={r.page} className="border-t border-[var(--border)] text-right"><td className="max-w-xs truncate py-2.5 text-left" title={r.page}>{r.page.replace(/^https?:\/\/[^/]+/, "") || "/"}</td><td>{num(r.sessions)}</td><td>{num(r.previous)}</td><td>{num(r.key_actions)}</td></tr>)}
            </tbody>
          </table>
        </Section>
      ) : null}

      {p.ai_assistants.length ? (
        <Section title="Visits from AI assistants" sentence="Counted only where the visit says it came from an AI assistant. It is never guessed from direct visits.">
          <table className="w-full text-sm">
            <thead><tr className="text-right"><th className={`${th} text-left`}>Assistant</th><th className={th}>{monthName(p.month)}</th><th className={th}>{monthName(p.previous_month)}</th><th className={th}>Change</th><th className={th}>Key actions</th></tr></thead>
            <tbody className="tabular-nums">
              {p.ai_assistants.map((r) => <tr key={r.label} className="border-t border-[var(--border)] text-right"><td className="py-2.5 text-left">{r.label}</td><td>{num(r.sessions)}</td><td>{num(r.previous)}</td><td><Delta pct={r.change_pct} none="new" /></td><td>{r.key_actions == null ? "–" : num(r.key_actions)}</td></tr>)}
            </tbody>
          </table>
        </Section>
      ) : null}
    </div>
  );
}
