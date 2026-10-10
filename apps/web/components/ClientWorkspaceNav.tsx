import Link from "next/link";

import { clientHref } from "@/lib/client-path";

/**
 * In the order a client is set up, which is the order the data depends on.
 *
 * Integrations came after Settings when Settings was where you began. It is
 * not: nothing on it can be filled in usefully before a source is connected
 * and pulled, and the lead definitions screen has no event names to offer
 * until GA4's first pull has landed. Setup is the first thing on Settings,
 * and it links onward from there.
 */
const WORKSPACE_LINKS = [
  { segment: "", label: "Setup" },
  { segment: "integrations", label: "Integrations" },
  { segment: "jobs", label: "Sync jobs" },
  { segment: "data-health", label: "Data health" },
  { segment: "conversions", label: "Conversions" },
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
