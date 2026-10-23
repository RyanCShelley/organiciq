import type { DashboardExploration, DashboardResponse } from "./dashboard";

export function engagementRate(
  channels: DashboardResponse["traffic"]["by_channel"] | null | undefined,
) {
  const known = (channels ?? []).filter((row) => row.bounce_rate != null);
  const visits = known.reduce((sum, row) => sum + row.sessions, 0);
  return visits
    ? 100 - known.reduce((sum, row) => sum + row.sessions * row.bounce_rate!, 0) / visits
    : null;
}

export function promptComparison(
  current: DashboardExploration["prompts"],
  previous: DashboardExploration["prompts"],
  metric: "mentioned" | "cited",
) {
  const key = (row: DashboardExploration["prompts"][number]) =>
    JSON.stringify([row.provider, row.prompt_id ?? row.prompt]);
  const before = new Map(previous.map((row) => [key(row), row]));
  const matched = current.filter(
    (row) => row[metric] != null && before.get(key(row))?.[metric] != null,
  );
  return {
    count: matched.length,
    current: matched.length
      ? 100 * matched.filter((row) => row[metric]).length / matched.length
      : null,
    previous: matched.length
      ? 100 * matched.filter((row) => before.get(key(row))![metric]).length / matched.length
      : null,
  };
}

export function pointChange(
  current: number | null | undefined,
  previous: number | null | undefined,
) {
  if (current == null || previous == null) return "No comparison";
  const value = current - previous;
  return `${value > 0 ? "+" : ""}${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} pp`;
}
