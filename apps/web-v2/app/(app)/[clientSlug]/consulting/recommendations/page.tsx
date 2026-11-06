import { notFound } from "next/navigation";

import { RecommendationQueue } from "@/components/RecommendationQueue";
import { ApiError, apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import type { RecList } from "@/lib/portal";

export const metadata = { title: "Recommendations" };

export default async function RecommendationsPage({ params, searchParams }: { params: Promise<{ clientSlug: string }>; searchParams: Promise<{ state?: string }> }) {
  const { clientSlug } = await params;
  const { state } = await searchParams;
  const client = await findClient(clientSlug);
  if (!client) notFound();
  let data: RecList | null = null;
  let error: string | null = null;
  try {
    data = await apiFetch<RecList>(`/v2/consulting/recommendations${state ? `?${new URLSearchParams({ state })}` : ""}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The recommendations could not be loaded: the API did not answer.";
  }
  return <RecommendationQueue client={client} data={data} error={error} state={state ?? null} />;
}
