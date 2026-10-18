import type { BaselineSeriesRow } from "@/app/(app)/baseline-actions";

/**
 * One bar per month. Months in the baseline window are teal; months before the
 * baseline start are grey, so it is plain which months the numbers come from.
 */
export function MonthBars({
  rows,
  value,
  label,
}: {
  rows: BaselineSeriesRow[];
  value: (row: BaselineSeriesRow) => number | null;
  label: string;
}) {
  const values = rows.map((row) => value(row) ?? 0);
  const max = Math.max(1, ...values);
  const step = 14;
  const height = 56;
  return (
    <figure className="m-0">
      <figcaption className="mb-1 text-xs font-semibold text-[var(--text-secondary)]">{label}</figcaption>
      <svg
        viewBox={`0 0 ${rows.length * step} ${height + 12}`}
        className="h-[84px] w-full"
        role="img"
        aria-label={`${label} by month`}
        preserveAspectRatio="none"
      >
        {rows.map((row, index) => {
          const h = Math.max(1, (values[index] / max) * height);
          return (
            <g key={row.month}>
              <title>{`${row.month}: ${values[index].toLocaleString()}`}</title>
              <rect
                x={index * step + 2}
                y={height - h}
                width={step - 4}
                height={h}
                rx={1.5}
                fill={row.in_window ? "var(--brand-teal-deep, #0F766E)" : "var(--border-strong, #C9D1D8)"}
              />
            </g>
          );
        })}
      </svg>
      <div className="flex justify-between text-[10.5px] text-[var(--text-tertiary)]">
        <span>{rows[0]?.month}</span>
        <span>{rows[rows.length - 1]?.month}</span>
      </div>
    </figure>
  );
}
