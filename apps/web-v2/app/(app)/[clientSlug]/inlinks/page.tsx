import { notFound } from "next/navigation";

import { DataFreshness, freshnessFor } from "@/components/DataFreshness";
import { InlinkSuggester } from "@/components/InlinkSuggester";
import { ApiError, apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import type { InResponse } from "@/lib/inlinks";

export const metadata = { title: "Inlink suggester" };

export default async function InlinksPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  const freshness = freshnessFor(client.id);
  let result: InResponse | null = null;
  let error: string | null = null;
  try {
    result = await apiFetch<InResponse>("/v2/inlinks", { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The suggestions could not be built: the API did not answer.";
  }
  return (
    <>
      <DataFreshness clientId={client.id} pending={freshness} />
      <InlinkSuggester client={client} data={result?.data ?? null} error={error} />
    </>
  );
}
