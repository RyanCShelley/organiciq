import { notFound } from "next/navigation";

import { InlinkSuggester } from "@/components/InlinkSuggester";
import { ApiError, apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import type { InResponse } from "@/lib/inlinks";

export const metadata = { title: "Inlink suggester" };

export default async function InlinksPage({ params, searchParams }: { params: Promise<{ clientSlug: string }>; searchParams: Promise<{ q?: string }> }) {
  const { clientSlug } = await params;
  const { q } = await searchParams;
  const client = await findClient(clientSlug);
  if (!client) notFound();

  let result: InResponse | null = null;
  let error: string | null = null;
  try {
    result = await apiFetch<InResponse>(`/v2/inlinks${q?.trim() ? `?${new URLSearchParams({ q: q.trim() })}` : ""}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The suggestions could not be built: the API did not answer.";
  }
  return (
    <>
      <InlinkSuggester client={client} q={q?.trim() ?? ""} data={result?.data ?? null} error={error} />
    </>
  );
}
