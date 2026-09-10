import type { ReactNode } from "react";
import { Suspense } from "react";

import { AppTopBar } from "@/components/layout/AppTopBar";
import { SidebarNav } from "@/components/layout/SidebarNav";
import type { Client } from "@/lib/api";

export function AppShell({
  children,
  clients,
  clientId,
  from,
  to,
  userEmail,
  signOutAction,
}: {
  children: ReactNode;
  clients: Client[];
  clientId: string;
  from: string;
  to: string;
  userEmail?: string | null;
  signOutAction: () => Promise<void>;
}) {
  return (
    <div className="flex min-h-screen bg-[var(--background)]">
      <SidebarNav
        clients={clients}
        clientId={clientId}
        from={from}
        to={to}
        userEmail={userEmail}
        signOutAction={signOutAction}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 border-b border-[var(--border)] bg-[var(--surface)] px-7 py-3.5">
          <Suspense
            fallback={
              <div className="text-xs text-[var(--text-secondary)]">Loading workspace…</div>
            }
          >
            <AppTopBar clients={clients} clientId={clientId} from={from} to={to} />
          </Suspense>
        </header>

        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}
