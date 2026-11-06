import Link from "next/link";
import { notFound } from "next/navigation";

import { apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import type { Watchlist } from "@/lib/watchlist";

export const metadata = { title: "Watchlist" };

export default async function WatchlistPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = await findClient(clientSlug);
  if (!client) notFound();

  const watchlist = await apiFetch<Watchlist>("/v2/watchlist", { clientId: client.id });

  return (
    <section className="space-y-6">
      <header>
        <h2 className="font-[family-name:var(--font-display)] text-lg font-bold">Watchlist</h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {client.client_name} · {watchlist.buckets.length} buckets · {watchlist.keyword_count}{" "}
          keywords
        </p>
      </header>

      <p className="text-sm text-[var(--text-secondary)]">
        {watchlist.keyword_count === 0 ? "Nothing here yet. " : "To update this list, "}
        <Link
          href={`/${client.slug}/settings/watchlist`}
          className="font-semibold text-[var(--brand-teal)] hover:underline"
        >
          {watchlist.keyword_count === 0 ? "Import the watchlist in Settings →" : "re-import it in Settings →"}
        </Link>
      </p>

      {watchlist.buckets.map((bucket) => (
        <div key={bucket.id} className="rounded-xl border border-[var(--border)] bg-[var(--surface)]">
          <h2 className="border-b border-[var(--border)] px-5 py-3 text-sm font-semibold">
            {bucket.name}{" "}
            <span className="font-normal text-[var(--text-tertiary)]">
              · {bucket.keywords.length} keywords
            </span>
          </h2>
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
              <tr>
                <th className="px-5 py-2 font-medium">Keyword</th>
                <th className="px-3 py-2 text-right font-medium">Volume</th>
                <th className="px-3 py-2 text-right font-medium">KD</th>
                <th className="px-3 py-2 font-medium">Intent</th>
                <th className="px-5 py-2 font-medium">Paired AI prompt</th>
              </tr>
            </thead>
            <tbody>
              {bucket.keywords.map((row) => (
                <tr key={row.id} className="border-t border-[var(--border)] align-top">
                  <td className="px-5 py-2">{row.keyword}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {row.volume?.toLocaleString() ?? "–"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{row.difficulty ?? "–"}</td>
                  <td className="px-3 py-2 text-[var(--text-secondary)]">{row.intent ?? "–"}</td>
                  <td className="px-5 py-2 text-[var(--text-secondary)]">
                    {row.paired_ai_prompt ?? "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}
