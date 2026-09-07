import type { ReactNode } from "react";
import { Suspense } from "react";

import { DateRangeControls } from "@/components/layout/DateRangeControls";
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
        <header className="border-b border-[var(--border)] bg-[var(--surface)]">
          <div className="page-gutter-x app-topbar flex items-center">
            <Suspense
              fallback={
                <div className="text-xs text-[var(--text-secondary)]">Loading date range…</div>
              }
            >
              <DateRangeControls clientId={clientId} from={from} to={to} />
            </Suspense>
          </div>
        </header>

        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}
