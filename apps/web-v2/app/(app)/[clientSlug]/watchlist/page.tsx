import { notFound } from "next/navigation";

import { WatchlistEditor } from "@/components/WatchlistEditor";
import { apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import type { Watchlist, WatchlistSuggestionsResponse } from "@/lib/watchlist";

export const metadata = { title: "Watchlist" };

export default async function WatchlistPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = await findClient(clientSlug);
  if (!client) notFound();

  const [watchlist, suggestions] = await Promise.all([
    apiFetch<Watchlist>("/v2/watchlist", { clientId: client.id }),
    apiFetch<WatchlistSuggestionsResponse>("/v2/watchlist/suggestions?days=90&limit=30", {
      clientId: client.id,
    }).catch((): WatchlistSuggestionsResponse | null => null),
  ]);

  return (
    <WatchlistEditor
      clientId={client.id}
      clientSlug={client.slug}
      clientName={client.client_name}
      initialWatchlist={watchlist}
      initialSuggestions={suggestions}
    />
  );
}
