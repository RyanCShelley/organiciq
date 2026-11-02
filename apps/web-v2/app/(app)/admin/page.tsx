import Link from "next/link";

import { AdminClients } from "@/components/AdminClients";
import { ApiError, apiFetch } from "@/lib/api";
import type { AdminClient } from "@/lib/admin";

export const metadata = { title: "Admin" };

export default async function AdminPage() {
  let clients: AdminClient[] = [];
  let error: string | null = null;
  try {
    clients = await apiFetch<AdminClient[]>("/v2/admin/clients");
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
            Every client, what is set up for it, and how current its data is. {clients.length ? `${clients.length} clients.` : ""}
          </p>
        </div>
        {!error ? (
          <Link href="/new-client" className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white">
            Add a client
          </Link>
        ) : null}
      </header>
      {error ? (
        <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">
          {error}
        </p>
      ) : (
        <AdminClients clients={clients} />
      )}
    </section>
  );
}
