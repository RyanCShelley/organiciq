import { notFound } from "next/navigation";

import { DataFreshness, freshnessFor } from "@/components/DataFreshness";
import { SchemaScreen } from "@/components/SchemaScreen";
import { ApiError, apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import type { ScResponse } from "@/lib/schema";

export const metadata = { title: "Schema & knowledge graph" };

export default async function SchemaPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  const freshness = freshnessFor(client.id);
  let result: ScResponse | null = null;
  let error: string | null = null;
  try {
    result = await apiFetch<ScResponse>("/v2/schema", { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "Schema could not be read: the API did not answer.";
  }
  return (
    <>
      <DataFreshness clientId={client.id} pending={freshness} />
      <SchemaScreen client={client} result={result} error={error} />
    </>
  );
}
