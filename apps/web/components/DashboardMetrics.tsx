import type { ReactNode } from "react";

import { Alert } from "@/components/ui/Alert";
import { MetricCard } from "@/components/analytics/MetricCard";
import { SectionHeader } from "@/components/ui/SectionHeader";
import type { DashboardFreshness, DashboardPeriodMetric } from "@/lib/dashboard";

export function DashboardMetricCard(props: {
  label: string;
  metric?: DashboardPeriodMetric;
  unit?: "count" | "pct" | "position" | "visibility";
  invertChange?: boolean;
  hint?: string;
  countLabel?: string;
  countValue?: number | null;
}) {
  return <MetricCard {...props} />;
}

export function DashboardSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="workspace-section">
      <SectionHeader title={title} description={description} />
      <div className="workspace-panel">{children}</div>
    </section>
  );
}

export function FreshnessBanner({ rows }: { rows: DashboardFreshness[] }) {
  const stale = rows.filter((row) => !row.available);
  if (stale.length === 0) return null;

  return (
    <Alert variant="warning">
      Some sources have no validated data for this period:{" "}
      {stale.map((row) => row.source.replaceAll("_", " ")).join(", ")}.
    </Alert>
  );
}
