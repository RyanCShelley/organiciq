import { notFound } from "next/navigation";

import { Annotations } from "@/components/Annotations";
import { ApiError, apiFetch } from "@/lib/api";
import type { Completed } from "@/lib/annotations";
import { findClient } from "@/lib/clients";

export const metadata = { title: "Annotations" };

export default async function AnnotationsPage({ params, searchParams }: { params: Promise<{ clientSlug: string }>; searchParams: Promise<{ page?: string }> }) {
  const { clientSlug } = await params;
  const { page } = await searchParams;
  const client = await findClient(clientSlug);
  if (!client) notFound();

  let data: Completed | null = null;
  let error: string | null = null;
  try {
    data = await apiFetch<Completed>(`/v2/annotations${page ? `?${new URLSearchParams({ page })}` : ""}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The annotations could not be loaded: the API did not answer.";
  }
  return <Annotations client={client} data={data} error={error} page={page ?? null} />;
}
