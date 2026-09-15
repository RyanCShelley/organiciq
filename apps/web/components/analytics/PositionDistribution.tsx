import { cn } from "@/lib/cn";

/**
 * Where tracked keywords sit in the SERP, as a single stacked bar.
 *
 * Computed from the rows already on the page rather than a separate endpoint,
 * so the chart and the table below it can never disagree.
 */
export type PositionBand = {
  key: string;
  label: string;
  /** Inclusive lower bound; null means "not ranking". */
  min: number | null;
  max: number | null;
  className: string;
  dotClassName: string;
};

export const POSITION_BANDS: PositionBand[] = [
  {
    key: "top_3",
    label: "Top 3",
    min: 1,
    max: 3,
    className: "bg-[var(--brand-teal)]",
    dotClassName: "bg-[var(--brand-teal)]",
  },
  {
    key: "top_10",
    label: "4–10",
    min: 4,
    max: 10,
    className: "bg-[var(--brand-lime)]",
    dotClassName: "bg-[var(--brand-lime)]",
  },
  {
    key: "top_20",
    label: "11–20",
    min: 11,
    max: 20,
    className: "bg-[#d97706]",
    dotClassName: "bg-[#d97706]",
  },
  {
    key: "beyond_20",
    label: "21+",
    min: 21,
    max: null,
    className: "bg-[#909a9f]",
    dotClassName: "bg-[#909a9f]",
  },
  {
    key: "not_ranking",
    label: "Not ranking",
    min: null,
    max: null,
    className: "bg-[#d3d7d9]",
    dotClassName: "bg-[#d3d7d9]",
  },
];

export function bandFor(position: number | null): PositionBand {
  if (position === null || Number.isNaN(position) || position <= 0) {
    return POSITION_BANDS[POSITION_BANDS.length - 1];
  }
  for (const band of POSITION_BANDS) {
    if (band.min === null) continue;
    if (position >= band.min && (band.max === null || position <= band.max)) {
      return band;
    }
  }
  return POSITION_BANDS[POSITION_BANDS.length - 1];
}

export function distributionOf(positions: (number | null)[]): Record<string, number> {
  const counts: Record<string, number> = Object.fromEntries(
    POSITION_BANDS.map((band) => [band.key, 0]),
  );
  for (const position of positions) {
    counts[bandFor(position).key] += 1;
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

  const counts = distributionOf(positions);

  return (
    <div className={cn("card p-[var(--card-padding)]", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
          Position distribution
        </h3>
        <span className="text-xs text-[var(--text-tertiary)]">
          {total.toLocaleString()} tracked keyword{total === 1 ? "" : "s"}
        </span>
      </div>

      <div className="mt-3 flex h-3 w-full overflow-hidden rounded-full bg-[#F1F2F3]">
        {POSITION_BANDS.map((band) => {
          const count = counts[band.key];
          if (count === 0) return null;
          return (
            <div
              key={band.key}
              className={band.className}
              style={{ width: `${(count / total) * 100}%` }}
              title={`${band.label}: ${count}`}
            />
          );
        })}
      </div>

      <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
        {POSITION_BANDS.map((band) => {
          const count = counts[band.key];
          return (
            <div key={band.key} className="flex items-center gap-2">
              <span
                className={cn("h-2.5 w-2.5 shrink-0 rounded-sm", band.dotClassName)}
                aria-hidden
              />
              <dt className="text-xs text-[var(--text-secondary)]">{band.label}</dt>
              <dd className="text-xs font-bold tabular-nums text-[var(--text-primary)]">
                {count}
                <span className="ml-1 font-normal text-[var(--text-tertiary)]">
                  {((count / total) * 100).toFixed(0)}%
                </span>
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}
