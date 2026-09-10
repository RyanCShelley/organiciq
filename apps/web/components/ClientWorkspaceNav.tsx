import Link from "next/link";

import { clientHref } from "@/lib/client-path";

const WORKSPACE_LINKS = [
  { segment: "", label: "Settings" },
  { segment: "integrations", label: "Integrations" },
  { segment: "conversions", label: "Conversions" },
  { segment: "data-health", label: "Data health" },
  { segment: "jobs", label: "Sync jobs" },
];

export function ClientWorkspaceNav({
  clientSlug,
  active,
}: {
  clientSlug: string;
  active: string;
}) {
  return (
    <div className="segmented mb-4" role="group" aria-label="Client workspace sections">
      {WORKSPACE_LINKS.map((link) => {
        const href = clientHref(clientSlug, link.segment);
        const isActive = active === href;
        return (
          <Link
            key={href}
            href={href}
            aria-current={isActive ? "page" : undefined}
            className={isActive ? "segmented-item segmented-item-active" : "segmented-item"}
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
    <div className="card mb-4 flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
          Client workspace
        </p>
        <p className="mt-1 font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
          {clientName}
        </p>
        <p className="font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]">
          {domain}
        </p>
      </div>
      <Link href="/clients" className="btn btn-secondary">
        All clients
      </Link>
    </div>
  );
}
