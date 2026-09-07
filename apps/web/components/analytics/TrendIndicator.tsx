import { cn } from "@/lib/cn";

export function TrendIndicator({
  changePct,
  invert = false,
  comparisonLabel = "vs previous period",
  className,
  compact = false,
}: {
  changePct: number | null;
  invert?: boolean;
  comparisonLabel?: string;
  className?: string;
  compact?: boolean;
}) {
  if (changePct === null || Number.isNaN(changePct)) {
    return (
      <div className={cn(compact ? "text-xs" : "text-sm", "text-[var(--text-tertiary)]", className)}>
        <span>—</span>
        {!compact && comparisonLabel ? (
          <span className="mt-0.5 block text-xs">{comparisonLabel}</span>
        ) : null}
      </div>
    );
  }

  const isPositive = invert ? changePct < 0 : changePct > 0;
  const isNegative = invert ? changePct > 0 : changePct < 0;
  const isNeutral = changePct === 0;

  const sign = changePct > 0 ? "+" : "";
  const arrow = isPositive ? "↑" : isNegative ? "↓" : "→";
  const tone = isNeutral
    ? "text-[var(--text-tertiary)]"
    : isPositive
      ? "text-[var(--success)]"
      : "text-[var(--danger)]";

  return (
    <div className={cn(compact ? "text-xs leading-tight" : "text-sm", className)}>
      <span className={cn("font-medium", tone)}>
        {arrow} {sign}
        {Math.abs(changePct).toFixed(1)}%
      </span>
      <span className="ml-1.5 text-[var(--text-tertiary)]">{comparisonLabel}</span>
    </div>
  );
}
