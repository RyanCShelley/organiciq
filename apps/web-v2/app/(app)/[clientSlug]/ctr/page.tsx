import { notFound } from "next/navigation";

import { CtrOptimizer } from "@/components/CtrOptimizer";
import { DataFreshness, freshnessFor } from "@/components/DataFreshness";
import { ApiError, apiFetch } from "@/lib/api";
import { presets } from "@/lib/bi";
import { getClients } from "@/lib/clients";
import type { Ctr } from "@/lib/ctr";

export const metadata = { title: "CTR optimizer" };

const DATE = /^\d{4}-\d{2}-\d{2}$/;

export default async function CtrPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<{ from?: string; to?: string; q?: string }>;
}) {
  const { clientSlug } = await params;
  const { from, to, q } = await searchParams;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  const ranges = presets();
  const fallback = ranges.find((r) => r.key === "90") ?? ranges[0];
  const start = from && DATE.test(from) ? from : fallback.from;
  const end = to && DATE.test(to) ? to : fallback.to;

  const freshness = freshnessFor(client.id);
  let data: Ctr | null = null;
  let error: string | null = null;
  try {
    const params = new URLSearchParams({ from: start, to: end });
    if (q?.trim()) params.set("q", q.trim());
    data = await apiFetch<Ctr>(`/v2/ctr?${params}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The CTR optimizer could not be built: the API did not answer.";
  }
  return (
    <>
      <DataFreshness clientId={client.id} pending={freshness} />
      <CtrOptimizer client={client} from={start} to={end} q={q?.trim() ?? ""} data={data} error={error} />
    </>
  );
}
