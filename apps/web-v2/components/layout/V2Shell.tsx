import Link from "next/link";

import { LogoWordmark } from "@/components/brand/Logo";
import { ClientNav } from "@/components/layout/ClientNav";
import { ClientSelect } from "@/components/layout/ClientSelect";
import type { Client } from "@/lib/api";

/** What v2 will contain, in build order. Nothing links anywhere until its phase ships. */
export const V2_SECTIONS = [
  { label: "Decision Engine", phase: "Phase 1" },
  { label: "Dashboard", phase: "Phase 2" },
  { label: "Site Health", phase: "Phase 3" },
  { label: "Search Visibility", phase: "Phase 4" },
  { label: "CTR Optimizer", phase: "Phase 5" },
  { label: "LLM Visibility", phase: "Phase 6" },
  { label: "Content Hub", phase: "Phase 7" },
] as const;

export function V2Shell({
  clients,
  userEmail,
  signOutAction,
  children,
}: {
  clients: Client[];
  userEmail?: string | null;
  signOutAction: () => Promise<void>;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-4 bg-[var(--brand-dark)] px-5 py-3">
        <Link href="/" aria-label="Organic IQ v2 home">
          <LogoWordmark inverse className="text-xl" />
        </Link>
        <span className="rounded bg-[var(--brand-teal)] px-2 py-0.5 text-[0.65rem] font-bold uppercase tracking-wider text-white">
          v2
        </span>
        <div className="ml-4">
          <ClientSelect clients={clients} />
        </div>
        <Link href="/new-client" className="text-sm text-[var(--sidebar-fg-muted)] hover:text-white">
          + Add client
        </Link>
        <div className="ml-auto flex items-center gap-4 text-sm text-[var(--sidebar-fg-muted)]">
          {userEmail ? <span>{userEmail}</span> : null}
          <form action={signOutAction}>
            <button type="submit" className="text-white underline-offset-2 hover:underline">
              Sign out
            </button>
          </form>
        </div>
      </header>

      <div className="flex flex-1">
        <nav aria-label="Sections" className="w-56 shrink-0 border-r border-[var(--border)] bg-[var(--surface)] p-3">
          <ClientNav />
          <ul className="space-y-1">
            {V2_SECTIONS.map((section) => (
              <li
                key={section.label}
                className="flex items-center justify-between rounded-md px-3 py-2 text-sm text-[var(--text-tertiary)]"
              >
                <span>{section.label}</span>
                <span className="text-[0.65rem] uppercase tracking-wide">{section.phase}</span>
              </li>
            ))}
          </ul>
        </nav>
        <main className="flex-1 p-8">{children}</main>
      </div>
    </div>
  );
}
