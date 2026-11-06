import { notFound } from "next/navigation";

import { RecommendationEditor } from "@/components/RecommendationEditor";
import { ApiError, apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import type { Rec } from "@/lib/portal";

export const metadata = { title: "Recommendation" };

export default async function RecommendationPage({ params }: { params: Promise<{ clientSlug: string; id: string }> }) {
  const { clientSlug, id } = await params;
  const client = await findClient(clientSlug);
  if (!client) notFound();
  let rec: Rec | null = null;
  let error: string | null = null;
  if (id !== "new") {
    try {
      rec = await apiFetch<Rec>(`/v2/consulting/recommendations/${id}`, { clientId: client.id });
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) notFound();
      error = e instanceof ApiError ? e.message : "The brief could not be loaded: the API did not answer.";
    }
  }
  return <RecommendationEditor client={client} rec={rec} error={error} />;
}
