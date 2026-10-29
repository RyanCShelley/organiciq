import Link from "next/link";
import { notFound } from "next/navigation";

import { WatchlistImport } from "@/components/WatchlistImport";
import { apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import type { Watchlist } from "@/lib/watchlist";

export const metadata = { title: "Settings · Watchlist import" };

export default async function WatchlistImportPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();
  const watchlist = await apiFetch<Watchlist>("/v2/watchlist", { clientId: client.id });

  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--text-secondary)]">
        Currently {watchlist.buckets.length} buckets and {watchlist.keyword_count} keywords.{" "}
        <Link
          href={`/${client.slug}/watchlist`}
          className="font-semibold text-[var(--brand-teal)] hover:underline"
        >
          View the watchlist →
        </Link>
      </p>
      <WatchlistImport clientId={client.id} slug={client.slug} />
    </div>
  );
}
