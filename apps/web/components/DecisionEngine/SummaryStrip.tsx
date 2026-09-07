import Link from "next/link";

export function SummaryStrip({
  findingsCount,
  recommendedCount,
  planMin,
  additionalCount,
  contentOppHref,
  contentOppCount,
}: {
  findingsCount: number;
  recommendedCount: number;
  planMin: number;
  additionalCount: number;
  contentOppHref: string;
  contentOppCount: number;
}) {
  const links = [
    { href: "#recommended-actions", label: "Recommended Actions", count: recommendedCount },
    { href: "#growth-actions", label: "Growth Actions", count: null as number | null },
    { href: "#additional-findings", label: "Additional Findings", count: additionalCount },
    { href: contentOppHref, label: "Content Opp", count: contentOppCount },
  ];

  return (
    <div className="workspace-panel">
      <div className="metric-grid sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Findings" value={findingsCount} />
        <Stat label="Recommended Actions" value={recommendedCount} highlight />
        <Stat label="Plan floor" value={planMin} />
        <Stat label="Additional Findings" value={additionalCount} />
      </div>
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
  value: number;
  highlight?: boolean;
}) {
  return (
    <div>
      <div className="text-[0.625rem] font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]">
        {label}
      </div>
      <div
        className={`mt-0.5 font-[family-name:var(--font-display)] text-xl font-bold ${
          highlight ? "text-action-emphasis" : "text-[var(--text-primary)]"
        }`}
      >
        {value.toLocaleString()}
      </div>
    </div>
  );
}
