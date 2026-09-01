import { emptyPeriodMetric, type DashboardPeriodMetric } from "@/lib/dashboard";

function formatValue(
  value: number | null,
  unit?: "count" | "pct" | "position" | "visibility",
): string {
  if (value === null || Number.isNaN(value)) return "—";
  if (unit === "pct") return `${value.toFixed(2)}%`;
  if (unit === "position") return value.toFixed(1);
  if (unit === "visibility") return value.toFixed(2);
  if (Number.isInteger(value)) return value.toLocaleString();
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatChange(change: number | null): string {
  if (change === null || Number.isNaN(change)) return "—";
  const sign = change > 0 ? "+" : "";
  return `${sign}${change.toFixed(1)}%`;
}

function changeClass(change: number | null, invert = false): string {
  if (change === null || change === 0) return "text-[var(--muted)]";
  const positive = invert ? change < 0 : change > 0;
  return positive ? "text-emerald-400" : "text-rose-400";
}

export function DashboardMetricCard({
  label,
  metric,
  unit = "count",
  invertChange = false,
  hint,
  countLabel,
  countValue,
}: {
  label: string;
  metric?: DashboardPeriodMetric;
  unit?: "count" | "pct" | "position" | "visibility";
  invertChange?: boolean;
  hint?: string;
  countLabel?: string;
  countValue?: number | null;
}) {
  const safeMetric = metric ?? emptyPeriodMetric();
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
      <div className="text-sm text-[var(--muted)]">{label}</div>
      <div className="mt-2 text-2xl font-semibold">{formatValue(safeMetric.current, unit)}</div>
      {countLabel && countValue !== null && countValue !== undefined ? (
        <div className="mt-1 text-sm text-[var(--muted)]">
          {countLabel}: <span className="font-medium text-[var(--foreground)]">{countValue.toLocaleString()}</span>
        </div>
      ) : null}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--muted)]">
        <span>Prev {formatValue(safeMetric.previous, unit)}</span>
        <span className={changeClass(safeMetric.change_pct, invertChange)}>
          {formatChange(safeMetric.change_pct)}
        </span>
      </div>
      {hint ? <p className="mt-2 text-xs text-[var(--muted)]">{hint}</p> : null}
    </div>
  );
}

export function DashboardSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold">{title}</h2>
      {description ? <p className="mt-1 text-sm text-[var(--muted)]">{description}</p> : null}
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function FreshnessBanner({ rows }: { rows: DashboardFreshness[] }) {
  const stale = rows.filter((row) => !row.available);
  if (stale.length === 0) return null;

  return (
    <div className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
      Some sources have no validated data for this period:{" "}
      {stale.map((row) => row.source.replaceAll("_", " ")).join(", ")}. Metrics from those sources
      show as unavailable.
    </div>
  );
}
