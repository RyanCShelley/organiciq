import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import Link from "next/link";

import { apiFetch, type Client } from "@/lib/api";
import { auth, signOut } from "@/lib/auth";
import { defaultDateRange } from "@/lib/dates";
import { ClientDateControls } from "@/components/ClientDateControls";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/watch-list", label: "Watch List" },
  { href: "/decision-engine", label: "Decision Engine" },
  { href: "/activity", label: "Activity" },
  { href: "/client-strategy", label: "Client Strategy" },
  { href: "/platform", label: "Platform" },
  { href: "/clients", label: "Clients" },
];

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session) {
    redirect("/login");
  }

  const cookieStore = await cookies();
  const ranges = defaultDateRange(90);

  let clients: Client[] = [];
  try {
    clients = await apiFetch<Client[]>("/clients");
  } catch {
    clients = [];
  }

  const selectedClientId = cookieStore.get("oiq_client_id")?.value || clients[0]?.id || "";
  const from = cookieStore.get("oiq_from")?.value || ranges.from;
  const to = cookieStore.get("oiq_to")?.value || ranges.to;

  return (
    <div className="min-h-screen">
      <header className="border-b border-[var(--border)] bg-[var(--card)]">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-6">
            <Link href="/dashboard" className="text-lg font-semibold tracking-tight">
              Organic IQ
            </Link>
            <nav className="flex flex-wrap gap-3 text-sm text-[var(--muted)]">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={withContext(item.href, selectedClientId, from, to)}
                  className="hover:text-white"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-[var(--muted)]">{session.user?.email}</span>
            <form
              action={async () => {
                "use server";
                await signOut({ redirectTo: "/login" });
              }}
            >
              <button
                type="submit"
                className="rounded-lg border border-[var(--border)] px-3 py-1.5 hover:bg-white/5"
              >
                Sign out
              </button>
            </form>
          </div>
        </div>
        <div className="mx-auto max-w-7xl px-4 pb-3">
          <Suspense fallback={<div className="h-10 text-sm text-[var(--muted)]">Loading controls…</div>}>
            <ClientDateControls clients={clients} clientId={selectedClientId} from={from} to={to} />
          </Suspense>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}

function withContext(href: string, clientId: string, from: string, to: string): string {
  const params = new URLSearchParams();
  if (clientId) params.set("clientId", clientId);
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const qs = params.toString();
  return qs ? `${href}?${qs}` : href;
}
