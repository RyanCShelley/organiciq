import Link from "next/link";

import { AdminClients } from "@/components/AdminClients";
import { AdminTeamAccess } from "@/components/AdminTeamAccess";
import { ApiError, apiFetch } from "@/lib/api";
import type { AdminClient, TeamAccessData } from "@/lib/admin";

export const metadata = { title: "Admin" };

export default async function AdminPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab } = await searchParams;
  const team = tab === "team";
  let clients: AdminClient[] = [];
  let access: TeamAccessData | null = null;
  let error: string | null = null;
  try {
    if (team) access = await apiFetch<TeamAccessData>("/v2/admin/team-access");
    else clients = await apiFetch<AdminClient[]>("/v2/admin/clients");
  } catch (e) {
    error =
      e instanceof ApiError && e.status === 403
        ? "Only an SMA admin can manage clients."
        : e instanceof ApiError
          ? e.message
          : "The client list could not be loaded: the API did not answer.";
  }

  return (
    <section className="max-w-6xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">Admin</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {team ? "Who can see which clients." : `Every client, what is set up for it, and how current its data is. ${clients.length ? `${clients.length} clients.` : ""}`}
          </p>
        </div>
        {!error ? (
          <Link href="/new-client" className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white">
            Add a client
          </Link>
        ) : null}
      </header>
      <nav aria-label="Admin sections" className="flex gap-1 border-b border-[var(--border)]">
        {[{ label: "Clients", href: "/admin", on: !team }, { label: "Team access", href: "/admin?tab=team", on: team }].map((t) => (
          <Link key={t.label} href={t.href} aria-current={t.on ? "page" : undefined} className={`-mb-px border-b-2 px-3 py-2 text-[0.8125rem] font-semibold ${t.on ? "border-[var(--brand-teal)] text-[var(--brand-teal)]" : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}>{t.label}</Link>
        ))}
      </nav>
      {error ? (
        <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">
          {error}
        </p>
      ) : team && access ? (
        <AdminTeamAccess data={access} />
      ) : (
        <AdminClients clients={clients} />
      )}
    </section>
  );
}
