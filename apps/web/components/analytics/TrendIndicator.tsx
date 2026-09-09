import { cn } from "@/lib/cn";

export function TrendIndicator({
  changePct,
  invert = false,
  comparisonLabel = "vs previous period",
  comparisonValue,
  className,
  compact = false,
}: {
  changePct: number | null;
  invert?: boolean;
  comparisonLabel?: string;
  /** Absolute comparison figure (previous period or baseline). */
  comparisonValue?: string | null;
  className?: string;
  compact?: boolean;
}) {
  const comparisonText =
    comparisonValue && comparisonValue !== "—"
      ? `${comparisonLabel} ${comparisonValue}`
      : comparisonLabel;

  if (changePct === null || Number.isNaN(changePct)) {
    return (
      <div className={cn(compact ? "text-xs" : "text-sm", "text-[var(--text-tertiary)]", className)}>
        <span>—</span>
        {comparisonText ? (
          <span className={cn(compact ? "ml-1.5" : "mt-0.5 block text-xs")}>{comparisonText}</span>
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
      <span className="ml-1.5 text-[var(--text-tertiary)]">{comparisonText}</span>
    </div>
  );
}
