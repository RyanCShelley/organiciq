import { notFound, redirect } from "next/navigation";

import { findClient } from "@/lib/clients";

export const metadata = { title: "Settings · Watchlist" };

export default async function WatchlistImportPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = await findClient(clientSlug);
  if (!client) notFound();
  redirect(`/${client.slug}/watchlist`);
}
