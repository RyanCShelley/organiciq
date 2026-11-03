import { notFound } from "next/navigation";

import { DataFreshness, freshnessFor } from "@/components/DataFreshness";
import { SiteHealth } from "@/components/SiteHealth";
import { ApiError, apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import type { ShResponse } from "@/lib/site-health";

export const metadata = { title: "Site health" };

export default async function SiteHealthPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<{ month?: string }>;
}) {
  const { clientSlug } = await params;
  const { month } = await searchParams;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  const freshness = freshnessFor(client.id);
  let result: ShResponse | null = null;
  let error: string | null = null;
  try {
    const q = month && /^\d{4}-(0[1-9]|1[0-2])$/.test(month) ? `?month=${month}` : "";
    result = await apiFetch<ShResponse>(`/v2/site-health${q}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "Site health could not be read: the API did not answer.";
  }

  return (
    <>
      <DataFreshness clientId={client.id} pending={freshness} />
      <SiteHealth client={client} result={result} error={error} />
    </>
  );
}
