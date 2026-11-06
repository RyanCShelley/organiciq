import { card } from "@/components/portal/BriefParts";
import type { ReportData, ReportMetric } from "@/lib/portal";

const fmt = (n: number | null, unit: string) => (n == null ? "–" : `${Number.isInteger(n) ? n.toLocaleString() : n.toLocaleString(undefined, { maximumFractionDigits: 1 })}${unit === "%" ? "%" : ""}`);

function Change({ m }: { m: ReportMetric }) {
  if (m.change_pct == null) return null;
  const up = m.change_pct > 0;
  const good = m.lower_is_better ? !up : up;
  const flat = Math.abs(m.change_pct) < 2;
  return <span className={`text-xs font-semibold ${flat ? "text-[var(--text-secondary)]" : good ? "text-green-800" : "text-red-800"}`}>{up ? "▲" : "▼"} {Math.abs(Math.round(m.change_pct))}%</span>;
}

/** The headline numbers: this month against last, where each comes from, and what is missing. Shared by the consultant's page and the client's portal. */
export function ReportDataView({ data }: { data: ReportData }) {
  return (
    <div className="space-y-4">
      {data.headline ? <p className="text-base font-medium">{data.headline}</p> : null}
      <div className="grid gap-4 lg:grid-cols-3">
        {data.sections.map((s) => (
          <section key={s.key} className={`${card} p-4`}>
            <h3 className="text-sm font-bold">{s.label}</h3>
            <p className="text-xs text-[var(--text-secondary)]">{s.question}</p>
            {s.metrics.length ? (
              <ul className="mt-3 space-y-3">
                {s.metrics.map((m) => (
                  <li key={m.label}>
                    <div className="text-xs text-[var(--text-secondary)]">{m.label}</div>
                    <div className="flex items-baseline gap-2"><span className="text-2xl font-bold tabular-nums">{fmt(m.current, m.unit)}</span>{m.unit && m.unit !== "%" ? <span className="text-xs text-[var(--text-secondary)]">{m.unit}</span> : null}<Change m={m} /></div>
                    {m.previous != null ? <div className="text-xs text-[var(--text-tertiary)]">last month {fmt(m.previous, m.unit)}</div> : null}
                    <div className="text-[0.7rem] text-[var(--text-tertiary)]">{m.source}</div>
                    {m.note ? <div className="text-xs text-[var(--text-secondary)]">{m.note}</div> : null}
                  </li>
                ))}
              </ul>
            ) : null}
            {s.read ? <p className="mt-3 text-sm">{s.read}</p> : null}
            {s.limitation ? <p className="mt-3 rounded-lg bg-amber-50 p-2 text-xs text-amber-900">{s.limitation}</p> : null}
          </section>
        ))}
      </div>
      <ul className="space-y-0.5 text-xs text-[var(--text-secondary)]">{data.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
    </div>
  );
}
