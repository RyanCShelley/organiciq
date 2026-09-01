import Link from "next/link";

import { apiFetch, type Client } from "@/lib/api";

export default async function ClientsIndexPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const oauth = typeof params.oauth === "string" ? params.oauth : null;
  const oauthMessage = typeof params.message === "string" ? params.message : null;

  let clients: Client[] = [];
  let error: string | null = null;

  try {
    clients = await apiFetch<Client[]>("/clients");
  } catch (e) {
    const message = e instanceof Error ? e.message : "Failed to load clients";
    if (message.toLowerCase().includes("invalid or expired token")) {
      error = "Your API session expired. Refresh the page or sign in again.";
    } else {
      error = message;
    }
  }

  return (
    <section>
      <h1 className="text-2xl font-semibold">Clients</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Open one client workspace at a time to connect integrations, map properties, and configure
        conversions. Use Platform for cross-client data health and sync monitoring.
      </p>

      {oauth === "error" ? (
        <p className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          OAuth failed{oauthMessage ? `: ${oauthMessage}` : ""}
        </p>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          {error}
        </p>
      ) : null}

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {clients.map((client) => (
          <Link
            key={client.id}
            href={`/clients/${client.id}`}
            className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 hover:border-[var(--accent)]"
          >
            <div className="text-lg font-semibold">{client.client_name}</div>
            <div className="text-sm text-[var(--muted)]">{client.domain}</div>
            <div className="mt-3 text-sm text-[var(--accent)]">Open workspace →</div>
          </Link>
        ))}
      </div>

      {clients.length === 0 && !error ? (
        <p className="mt-6 text-sm text-[var(--muted)]">No clients yet.</p>
      ) : null}
    </section>
  );
}
