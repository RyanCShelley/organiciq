import { cn } from "@/lib/cn";

export function TrendIndicator({
  changePct,
  invert = false,
  comparisonLabel = "vs previous period",
  comparisonValue,
  className,
  compact = false,
  tone = "light",
}: {
  changePct: number | null;
  invert?: boolean;
  comparisonLabel?: string;
  /** Absolute comparison figure (previous period or baseline). */
  comparisonValue?: string | null;
  className?: string;
  compact?: boolean;
  tone?: "light" | "glass";
}) {
  const comparisonText =
    comparisonValue && comparisonValue !== "—"
      ? `${comparisonLabel} ${comparisonValue}`
      : comparisonLabel;

  if (changePct === null || Number.isNaN(changePct)) {
    return (
      <div
        className={cn(
          "flex flex-wrap items-center gap-2",
          compact ? "text-xs" : "text-sm",
          tone === "glass" ? "text-[var(--brand-on-dark)]" : "text-[var(--text-tertiary)]",
          className,
        )}
      >
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[11.5px] font-bold",
            tone === "glass"
              ? "bg-white/10 text-[var(--brand-on-dark)]"
              : "bg-[#F1F2F3] text-[var(--text-tertiary)]",
          )}
        >
          —
        </span>
        {comparisonText ? (
          <span className={cn(tone === "glass" ? "text-[var(--brand-on-dark)]" : "text-[var(--text-tertiary)]")}>
            {comparisonText}
          </span>
        ) : null}
      </div>
    );
  }

  const isPositive = invert ? changePct < 0 : changePct > 0;
  const isNegative = invert ? changePct > 0 : changePct < 0;
  const isNeutral = changePct === 0;

  const sign = changePct > 0 ? "+" : "";
  const arrow = isPositive ? "↑" : isNegative ? "↓" : "→";

  const pillClass = isNeutral
    ? tone === "glass"
      ? "bg-white/10 text-[var(--brand-on-dark)]"
      : "bg-[#F1F2F3] text-[var(--text-tertiary)]"
    : isPositive
      ? tone === "glass"
        ? "bg-transparent text-[var(--brand-lime)]"
        : "bg-[var(--success-soft)] text-[var(--success)]"
      : tone === "glass"
        ? "bg-transparent text-[#ff8f8f]"
        : "bg-[var(--danger-soft)] text-[var(--danger)]";

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <span className={cn("rounded-full px-2.5 py-0.5 text-[11.5px] font-bold", pillClass)}>
        {arrow} {sign}
        {Math.abs(changePct).toFixed(1)}%
      </span>
      <span
        className={cn(
          "text-xs",
          tone === "glass" ? "text-[var(--brand-on-dark)]" : "text-[var(--text-tertiary)]",
        )}
      >
        {comparisonText}
      </span>
    </div>
  );
}
