import type { ReactNode } from "react";

import { Card } from "@/components/ui/Card";
import { Sparkline } from "@/components/analytics/Sparkline";
import { TrendIndicator } from "@/components/analytics/TrendIndicator";
import { cn } from "@/lib/cn";
import { emptyPeriodMetric, type DashboardPeriodMetric } from "@/lib/dashboard";

type MetricUnit = "count" | "pct" | "position" | "visibility";

function formatValue(value: number | null, unit: MetricUnit): string {
  if (value === null || Number.isNaN(value)) return "—";
  if (unit === "pct") return `${value.toFixed(2)}%`;
  if (unit === "position") return value.toFixed(1);
  if (unit === "visibility") return value.toFixed(2);
  if (Number.isInteger(value)) return value.toLocaleString();
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function MetricCard({
  label,
  metric,
  unit = "count",
  invertChange = false,
  hint,
  comparisonLabel = "vs previous period",
  /** Compare mode "none": render the value and sparkline with no delta pill. */
  showComparison = true,
  countLabel,
  countValue,
  size = "default",
  tone = "light",
  className,
  footer,
}: {
  label: string;
  metric?: DashboardPeriodMetric;
  unit?: MetricUnit;
  invertChange?: boolean;
  hint?: string;
  comparisonLabel?: string;
  showComparison?: boolean;
  countLabel?: string;
  countValue?: number | null;
  size?: "default" | "compact";
  tone?: "light" | "glass";
  className?: string;
  footer?: ReactNode;
}) {
  const safeMetric = metric ?? emptyPeriodMetric();
  const isCompact = size === "compact";
  const isGlass = tone === "glass";

  const body = (
    <>
      <div
        className={cn(
          "text-[12.5px] font-semibold",
          isGlass ? "text-[var(--brand-on-dark)]" : "text-[var(--text-secondary)]",
        )}
      >
        {label}
      </div>
      <div className="mt-2.5 flex items-end justify-between gap-3.5">
        <div
          className={cn(
            "font-[family-name:var(--font-display)] font-black tracking-[-0.02em] leading-none",
            isCompact ? "text-[26px]" : "text-[32px]",
            isGlass ? "text-white" : "text-[var(--text-primary)]",
          )}
        >
          {formatValue(safeMetric.current, unit)}
        </div>
        <Sparkline
          values={safeMetric.series}
          invert={invertChange}
          width={isCompact ? 70 : 86}
          height={isCompact ? 26 : 30}
          stroke={isGlass ? "var(--brand-lime)" : undefined}
          fill={isGlass ? "rgb(170 228 55 / 16%)" : undefined}
        />
      </div>
      {countLabel && countValue !== null && countValue !== undefined ? (
        <div
          className={cn(
            "mt-1 text-xs",
            isGlass ? "text-[var(--brand-on-dark)]" : "text-[var(--text-secondary)]",
          )}
        >
          {countLabel}:{" "}
          <span className={cn("font-medium", isGlass ? "text-white" : "text-[var(--text-primary)]")}>
            {countValue.toLocaleString()}
          </span>
        </div>
      ) : null}
      {showComparison ? (
        <div className="mt-auto pt-2.5">
          <TrendIndicator
            changePct={safeMetric.change_pct}
            invert={invertChange}
            comparisonLabel={comparisonLabel}
            comparisonValue={formatValue(safeMetric.previous, unit)}
            compact
            tone={tone}
          />
        </div>
      ) : null}
      {footer}
    </>
  );

  if (isGlass) {
    return (
      <div className={cn("baseline-glass h-full", className)} title={hint}>
        {body}
      </div>
    );
  }

  return (
    <Card
      className={cn(
        "flex h-full flex-col",
        isCompact ? "p-[15px_17px]" : "p-[18px_20px]",
        className,
      )}
      title={hint}
    >
      {body}
    </Card>
  );
}
