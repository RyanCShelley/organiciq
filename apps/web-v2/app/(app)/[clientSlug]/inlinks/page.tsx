import { notFound } from "next/navigation";

import { PlanBanner } from "@/components/PlanBanner";
import { InlinkSuggester } from "@/components/InlinkSuggester";
import { ApiError, apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import type { InResponse } from "@/lib/inlinks";

export const metadata = { title: "Inlink suggester" };

export default async function InlinksPage({ params, searchParams }: { params: Promise<{ clientSlug: string }>; searchParams: Promise<{ q?: string; target?: string }> }) {
  const { clientSlug } = await params;
  const { q: asked, target } = await searchParams;
  // A link from the plan names the page: the list is narrowed to it, so it is there to open however far down the ranking it sits.
  const q = asked ?? (target ? (target.replace(/^https?:\/\/[^/]+/, "").replace(/\/+$/, "") || "/") : undefined);
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
      <PlanBanner doing="Add the links this page is missing." />
      <InlinkSuggester client={client} q={q?.trim() ?? ""} data={result?.data ?? null} error={error} />
    </>
  );
}
