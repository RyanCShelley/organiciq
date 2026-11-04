import { notFound } from "next/navigation";

import { ContentGaps } from "@/components/ContentGaps";
import { ApiError, apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import type { Gaps } from "@/lib/content";

export const metadata = { title: "Content gaps" };

export default async function ContentGapsPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<{ q?: string; ignored?: string }>;
}) {
  const { clientSlug } = await params;
  const { q, ignored } = await searchParams;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  let data: Gaps | null = null;
  let error: string | null = null;
  try {
    const query = new URLSearchParams();
    if (q?.trim()) query.set("q", q.trim());
    if (ignored) query.set("ignored", "true");
    data = await apiFetch<Gaps>(`/v2/content/gaps${query.size ? `?${query}` : ""}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The content gaps could not be built: the API did not answer.";
  }
  return (
    <>
      <ContentGaps client={client} q={q?.trim() ?? ""} ignored={!!ignored} data={data} error={error} />
    </>
  );
}
