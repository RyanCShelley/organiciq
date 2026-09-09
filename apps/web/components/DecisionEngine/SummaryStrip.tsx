import Link from "next/link";

export function SummaryStrip({
  findingsCount,
  recommendedCount,
  planMin,
  reviewCount,
  contentOppHref,
  contentOppCount,
}: {
  findingsCount: number;
  recommendedCount: number;
  planMin: number;
  reviewCount: number;
  contentOppHref: string;
  contentOppCount: number;
}) {
  const links = [
    { href: "#growth-actions", label: "Growth Actions", count: null as number | null },
    { href: "#recommended-actions", label: "Engine shortlist", count: recommendedCount },
    { href: "#findings-review", label: "All findings", count: reviewCount },
    { href: contentOppHref, label: "Content Opp", count: contentOppCount },
  ];

  return (
    <div className="workspace-panel">
      <div className="metric-grid sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Findings" value={findingsCount} />
        <Stat label="Engine shortlist" value={recommendedCount} highlight />
        <Stat label="Plan floor" value={planMin} />
        <Stat label="For your review" value={reviewCount} />
      </div>
      <p className="mt-2 text-xs text-[var(--text-secondary)]">
        The engine promotes a shortlist. Open All findings to override — Accept any row even if it
        was not promoted.
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
