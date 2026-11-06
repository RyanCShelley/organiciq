import { CoverageDonut } from "@/components/bi/Charts";
import { StatCard } from "@/components/review/Sections";
import type { Bi } from "@/lib/bi";

const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

/** "Where are we showing up?": search ranking coverage and what AI answers say, from Insights, over the report's month. */
export function ShowingUp({ keywords, ai }: { keywords: Bi["keywords"] | null; ai: Bi["ai"] }) {
  const cov = keywords?.coverage;
  const moved = keywords?.keywords ?? [];
  const improved = moved.filter((k) => k.state === "up" || k.state === "new").length;
  const declined = moved.filter((k) => k.state === "down" || k.state === "lost").length;
  if (!cov && !ai) return null;
  const rate = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 10) / 10}%`);
  return (
    <section>
      <h2 className="mb-1 text-base font-bold">Where are we showing up?</h2>
      <p className="mb-3 text-sm text-[var(--text-secondary)]">Search rankings and AI answers are separate measures of visibility.</p>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-[var(--border)] bg-white p-5">
          <h3 className="text-sm font-semibold">Search ranking coverage</h3>
          {cov ? (
            <>
              <div className="mt-3"><CoverageDonut bands={cov.end} tracked={cov.tracked} /></div>
              <p className="mt-3 text-xs text-[var(--text-secondary)]"><strong>{improved}</strong> improving, <strong>{declined}</strong> declining, of {cov.tracked} tracked keywords.{keywords?.to ? ` Positions on ${day(keywords.to)}.` : ""} A keyword not found in the top 100 counts as outside.</p>
            </>
          ) : (
            <p className="mt-3 text-sm text-[var(--text-secondary)]">The rank tracker has no check inside this month.</p>
          )}
        </div>
        <div className="rounded-2xl border border-[var(--border)] bg-white p-5">
          <h3 className="text-sm font-semibold">AI mentions and citations</h3>
          {ai ? (
            <>
              <div className="mt-3 flex flex-wrap gap-8">
                <div><div className="text-3xl font-bold tabular-nums">{rate(ai.mention_rate)}</div><div className="text-xs text-[var(--text-secondary)]">answers that name the brand</div></div>
                <div><div className="text-3xl font-bold tabular-nums">{rate(ai.cited_rate)}</div><div className="text-xs text-[var(--text-secondary)]">answers that cite the site</div></div>
              </div>
              <table className="mt-4 w-full text-sm">
                <thead><tr className="text-left text-xs uppercase tracking-wide text-[var(--text-tertiary)]"><th className="py-1">Platform</th><th>Named</th><th>Cited</th><th>Checks</th></tr></thead>
                <tbody>{ai.platforms.map((p) => <tr key={p.platform} className="border-t border-[var(--border)]"><td className="py-1.5 font-medium">{p.platform}</td><td>{p.mentioned}</td><td>{p.cited}</td><td>{p.checks}</td></tr>)}</tbody>
              </table>
              <p className="mt-2 text-xs text-[var(--text-tertiary)]">A sample from the run on {day(ai.date)}{ai.date_before ? `, against the run on ${day(ai.date_before)}` : ""}, not every AI answer. Questions that name the brand are left out.</p>
            </>
          ) : (
            <p className="mt-3 text-sm text-[var(--text-secondary)]">No AI visibility run has finished for this month.</p>
          )}
        </div>
      </div>
    </section>
  );
}
