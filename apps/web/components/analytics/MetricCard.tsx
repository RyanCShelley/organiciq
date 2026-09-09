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
  countLabel,
  countValue,
  size = "default",
  className,
  footer,
}: {
  label: string;
  metric?: DashboardPeriodMetric;
  unit?: MetricUnit;
  invertChange?: boolean;
  hint?: string;
  comparisonLabel?: string;
  countLabel?: string;
  countValue?: number | null;
  size?: "default" | "compact";
  className?: string;
  footer?: ReactNode;
}) {
  const safeMetric = metric ?? emptyPeriodMetric();
  const isCompact = size === "compact";

  return (
    <Card
      className={cn(
        "flex h-full flex-col",
        isCompact ? "p-3" : "p-[var(--card-padding)]",
        className,
      )}
      title={hint}
    >
      <div className="text-xs font-medium text-[var(--text-secondary)]">{label}</div>
      <div className="mt-1 flex items-start justify-between gap-3">
        <div
          className={cn(
            "font-[family-name:var(--font-display)] font-bold tracking-tight text-[var(--text-primary)]",
            isCompact ? "text-lg" : "text-xl",
          )}
        >
          {formatValue(safeMetric.current, unit)}
        </div>
        <Sparkline
          values={safeMetric.series}
          invert={invertChange}
          width={isCompact ? 56 : 72}
          height={isCompact ? 22 : 28}
          className="mt-0.5"
        />
      </div>
      {countLabel && countValue !== null && countValue !== undefined ? (
        <div className="mt-0.5 text-xs text-[var(--text-secondary)]">
          {countLabel}:{" "}
          <span className="font-medium text-[var(--text-primary)]">
            {countValue.toLocaleString()}
          </span>
        </div>
      ) : null}
      <div className="mt-auto pt-2">
        <TrendIndicator
          changePct={safeMetric.change_pct}
          invert={invertChange}
          comparisonLabel={comparisonLabel}
          comparisonValue={formatValue(safeMetric.previous, unit)}
          compact
        />
      </div>
      {footer}
    </Card>
  );
}
