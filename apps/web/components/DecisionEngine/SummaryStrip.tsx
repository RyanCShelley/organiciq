import Link from "next/link";

export function SummaryStrip({
  findingsCount,
  recommendationsCount,
  selectedCount,
  growthPlanAllowance,
  suggestedCount,
  contentOppHref,
  contentOppCount,
}: {
  findingsCount: number;
  recommendationsCount: number;
  selectedCount: number;
  growthPlanAllowance: number;
  suggestedCount: number;
  contentOppHref: string;
  contentOppCount: number;
}) {
  const selectedLabel =
    growthPlanAllowance > 0
      ? `${selectedCount.toLocaleString()} / ${growthPlanAllowance.toLocaleString()}`
      : selectedCount.toLocaleString();

  const links = [
    { href: "#recommended-actions", label: "Recommendations", count: recommendationsCount },
    ...(suggestedCount > 0
      ? [{ href: "#suggested-alternatives", label: "Suggested", count: suggestedCount }]
      : []),
    { href: "#findings-review", label: "All findings", count: findingsCount },
    { href: contentOppHref, label: "Content Opp", count: contentOppCount },
  ];

  return (
    <div className="workspace-panel">
      <div className="metric-grid sm:grid-cols-3">
        <Stat label="Findings" value={findingsCount.toLocaleString()} />
        <Stat label="Recommendations" value={recommendationsCount.toLocaleString()} highlight />
        <Stat label="Selected toward plan" value={selectedLabel} />
      </div>
      <p className="mt-2 text-xs text-[var(--text-secondary)]">
        Recommendations cleared the engine thresholds. Suggested alternatives are optional extras.
        Accept items in All findings to count them toward your growth plan.
      </p>
      <nav className="mt-3 flex flex-wrap gap-1.5 border-t border-[var(--border)] pt-3">
        {links.map((link) => (
          <Link key={link.href} href={link.href} className="btn btn-ghost btn-sm">
            {link.label}
            {link.count != null ? ` (${link.count})` : ""}
          </Link>
        ))}
      </nav>
    </div>
  );
}

function Stat({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div>
      <div className="text-[0.625rem] font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]">
        {label}
      </div>
      <div
        className={`mt-0.5 font-[family-name:var(--font-display)] text-xl font-bold tabular-nums ${
          highlight ? "text-action-emphasis" : "text-[var(--text-primary)]"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
