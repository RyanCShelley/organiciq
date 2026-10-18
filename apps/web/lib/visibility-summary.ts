import type { Measurements } from "@/components/DecisionEngine/MeasurementSummary";

export function visibilitySummary(keywords: Measurements["visibility"]["keywords"] = []) {
  const priority = keywords.filter(term => term.priority);
  const measuredPriority = priority.filter(term => term.status !== "not_measured");
  const measuredAll = keywords.filter(term => term.status !== "not_measured");
  const measured = measuredPriority.length ? measuredPriority : measuredAll;
  const topTen = measured.filter(term => term.position != null && term.position <= 10).length;
  return {
    value: measured.length ? `${topTen} of ${measured.length}` : keywords.length ? "No dated rankings" : "No tracked keywords",
    label: measuredPriority.length ? "Measured priority keywords in the top 10" : "Measured tracked keywords in the top 10",
    note: !keywords.length ? "Connect SE Ranking and sync tracked keywords." : !measured.length
      ? "Sync ranking history for this assessment period; current positions may be from a later month."
      : !priority.length ? "No priority keywords selected; showing all measured tracked keywords."
      : !measuredPriority.length ? "Priority keywords have no dated readings; showing other measured tracked keywords."
      : priority.length > measuredPriority.length ? `${priority.length - measuredPriority.length} priority terms still unmeasured` : null,
  };
}
