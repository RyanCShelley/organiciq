import type { Measurements } from "@/components/DecisionEngine/MeasurementSummary";

export function visibilitySummary(keywords: Measurements["visibility"]["keywords"] = []) {
  const measured = keywords.filter(term => term.status !== "not_measured");
  const topTen = measured.filter(term => term.position != null && term.position <= 10).length;
  return {
    value: measured.length ? `${topTen} of ${measured.length}` : keywords.length ? "No dated rankings" : "No tracked keywords",
    label: "Measured target keywords in the top 10",
    note: !keywords.length ? "Connect SE Ranking and sync tracked keywords." : !measured.length
      ? "Sync ranking history for this assessment period; current positions may be from a later month."
      : keywords.length > measured.length ? `${keywords.length - measured.length} target keywords still unmeasured` : null,
  };
}
