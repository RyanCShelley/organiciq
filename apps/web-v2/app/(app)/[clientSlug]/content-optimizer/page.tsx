import { notFound } from "next/navigation";

import { ContentOptimizer } from "@/components/ContentOptimizer";
import { PlanBanner } from "@/components/PlanBanner";
import { ApiError, apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import type { OptQueue } from "@/lib/optimizer";

export const metadata = { title: "Content optimizer" };

export default async function ContentOptimizerPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = await findClient(clientSlug);
  if (!client) notFound();

  let data: OptQueue | null = null;
  let error: string | null = null;
  try {
    data = await apiFetch<OptQueue>("/v2/optimizer", { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The content optimizer could not be loaded: the API did not answer.";
  }
  return (
    <>
      <PlanBanner doing="Make the change for this page." />
      <ContentOptimizer client={client} data={data} error={error} />
    </>
  );
}
