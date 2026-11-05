import Link from "next/link";
import { notFound } from "next/navigation";

import { FocusForm } from "@/components/FocusForm";
import { apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import { type ClientFocus, FOCUSES, currentMonth, monthLabel } from "@/lib/focus";
import type { Watchlist } from "@/lib/watchlist";

export const metadata = { title: "Focus" };

export default async function FocusPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<{ month?: string }>;
}) {
  const { clientSlug } = await params;
  const { month: requested } = await searchParams;
  const client = await findClient(clientSlug);
  if (!client) notFound();

  const month = requested && /^\d{4}-(0[1-9]|1[0-2])$/.test(requested) ? requested : currentMonth();

  const [current, history, watchlist] = await Promise.all([
    apiFetch<ClientFocus | null>(`/v2/focus/${month}`, { clientId: client.id }),
    apiFetch<ClientFocus[]>("/v2/focus", { clientId: client.id }),
    apiFetch<Watchlist>("/v2/watchlist", { clientId: client.id }),
  ]);

  return (
    <section className="max-w-3xl space-y-8">
      <header>
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">Focus</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {client.client_name}. One focus and one watchlist bucket per month.
        </p>
      </header>

      {/* key: switching month remounts the form so it shows that month's saved focus. */}
      <FocusForm
        key={month}
        clientId={client.id}
        slug={client.slug}
        month={month}
        current={current}
        buckets={watchlist.buckets.map((b) => ({ id: b.id, name: b.name }))}
      />

      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
        <h2 className="text-sm font-semibold">Past and planned months</h2>
        <ul className="mt-3 divide-y divide-[var(--border)] text-sm">
          {history.length === 0 ? (
            <li className="py-2 text-[var(--text-tertiary)]">No focus saved yet.</li>
          ) : (
            history.map((row) => (
              <li key={row.month} className="flex items-center justify-between gap-4 py-2">
                <Link href={`/${client.slug}/focus?month=${row.month}`} className="font-medium hover:underline">
                  {monthLabel(row.month)}
                </Link>
                <span className="text-[var(--text-secondary)]">
                  {FOCUSES.find((f) => f.value === row.focus)?.label}
                  {row.bucket_name ? ` · ${row.bucket_name}` : ""}
                </span>
              </li>
            ))
          )}
        </ul>
      </div>
    </section>
  );
}
