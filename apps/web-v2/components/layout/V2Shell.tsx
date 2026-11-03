import Link from "next/link";

import { LogoWordmark } from "@/components/brand/Logo";
import { ClientNav, SidebarFooter } from "@/components/layout/ClientNav";
import { ClientSelect } from "@/components/layout/ClientSelect";
import type { Client } from "@/lib/api";

export function V2Shell({
  clients,
  userEmail,
  isAdmin = false,
  signOutAction,
  children,
}: {
  clients: Client[];
  userEmail?: string | null;
  isAdmin?: boolean;
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
        <nav aria-label="Sections" className="flex w-60 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] p-3">
          <ClientNav />
          <SidebarFooter isAdmin={isAdmin} />
        </nav>
        <main className="flex-1 p-8">{children}</main>
      </div>
    </div>
  );
}
