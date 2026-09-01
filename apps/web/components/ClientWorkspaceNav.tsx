import Link from "next/link";

const WORKSPACE_LINKS = [
  { segment: "", label: "Overview" },
  { segment: "integrations", label: "Integrations" },
  { segment: "conversions", label: "Conversions" },
  { segment: "data-health", label: "Data Health" },
  { segment: "jobs", label: "Sync Jobs" },
];

export function ClientWorkspaceNav({
  clientId,
  active,
}: {
  clientId: string;
  active: string;
}) {
  return (
    <div className="mb-6 flex flex-wrap gap-2">
      {WORKSPACE_LINKS.map((link) => {
        const href =
          link.segment === ""
            ? `/clients/${clientId}`
            : `/clients/${clientId}/${link.segment}`;
        const isActive = active === href;
        return (
          <Link
            key={href}
            href={href}
            className={`rounded-lg px-3 py-1.5 text-sm ${
              isActive
                ? "bg-[var(--accent)] text-white"
                : "border border-[var(--border)] text-[var(--muted)] hover:text-white"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </div>
  );
}

export function ClientWorkspaceHeader({
  clientName,
  domain,
}: {
  clientName: string;
  domain: string;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-white/5 px-4 py-3">
      <div>
        <p className="text-xs uppercase tracking-wide text-[var(--muted)]">Client workspace</p>
        <p className="text-lg font-semibold">{clientName}</p>
        <p className="text-sm text-[var(--muted)]">{domain}</p>
      </div>
      <Link
        href="/clients"
        className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm hover:bg-white/5"
      >
        All clients
      </Link>
    </div>
  );
}
