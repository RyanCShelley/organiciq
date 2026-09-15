import { cn } from "@/lib/cn";

/**
 * Where tracked keywords sit in the SERP.
 *
 * Bands are **cumulative** (TOP 10 includes TOP 3), matching how SE Ranking
 * reports it — "how many are on page one" is the question people actually ask,
 * and exclusive buckets make you add them up yourself.
 *
 * Computed from the rows already on the page rather than a separate endpoint,
 * so this and the table below it cannot disagree.
 */
export type PositionBand = {
  key: string;
  label: string;
  /** Inclusive upper bound; null means "not ranking". */
  max: number | null;
};

export const POSITION_BANDS: PositionBand[] = [
  { key: "top_1", label: "Top 1", max: 1 },
  { key: "top_3", label: "Top 3", max: 3 },
  { key: "top_5", label: "Top 5", max: 5 },
  { key: "top_10", label: "Top 10", max: 10 },
  { key: "top_30", label: "Top 30", max: 30 },
  { key: "not_ranking", label: "Not ranking", max: null },
];

function isRanking(position: number | null): position is number {
  return position !== null && !Number.isNaN(position) && position > 0;
}

export function countsFor(positions: (number | null)[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const band of POSITION_BANDS) {
    counts[band.key] =
      band.max === null
        ? positions.filter((p) => !isRanking(p)).length
        : positions.filter((p) => isRanking(p) && p <= band.max!).length;
  }
  return counts;
}

export function PositionDistribution({
  positions,
  className,
}: {
  positions: (number | null)[];
  className?: string;
}) {
  const total = positions.length;
  if (total === 0) return null;

  const counts = countsFor(positions);
  const pct = (n: number) => (total > 0 ? (n / total) * 100 : 0);

  return (
    <div className={cn("card p-[var(--card-padding)]", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
          Position distribution
        </h3>
        <span className="text-xs text-[var(--text-tertiary)]">
          Bands are cumulative · {total.toLocaleString()} tracked keyword
          {total === 1 ? "" : "s"}
        </span>
      </div>

      <div className="mt-3 overflow-x-auto">
        <div className="flex min-w-[34rem]">
          {/* ALL sits apart as the denominator the rest are read against. */}
          <div className="flex min-w-[5.5rem] flex-col items-center justify-end rounded-l-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--brand-dark-3)] px-3 py-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-white/60">
              All
            </span>
            <span className="mt-0.5 font-[family-name:var(--font-display)] text-[17px] font-black leading-none text-white">
              {total.toLocaleString()}
            </span>
          </div>

          {POSITION_BANDS.map((band, index) => {
            const count = counts[band.key];
            const share = pct(count);
            const last = index === POSITION_BANDS.length - 1;
            return (
              <div
                key={band.key}
                className={cn(
                  "flex min-w-[5.5rem] flex-1 flex-col items-center justify-end border-y border-r border-[var(--border-strong)] bg-white px-3 py-2",
                  last && "rounded-r-[var(--radius-md)]",
                )}
              >
                <span
                  className={cn(
                    "text-[11px] font-semibold tabular-nums",
                    count > 0 ? "text-[var(--text-secondary)]" : "text-[var(--text-tertiary)]",
                  )}
                >
                  {share.toFixed(share < 1 && share > 0 ? 1 : 0)}%
                </span>
                <span className="mt-0.5 text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--text-tertiary)]">
                  {band.label}
                </span>
                <span
                  className={cn(
                    "mt-0.5 font-[family-name:var(--font-display)] text-[17px] font-black leading-none tabular-nums",
                    count > 0 ? "text-[var(--text-primary)]" : "text-[var(--text-tertiary)]",
                  )}
                >
                  {count.toLocaleString()}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
