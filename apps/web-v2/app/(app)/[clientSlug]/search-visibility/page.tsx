import { notFound } from "next/navigation";

import { DataFreshness } from "@/components/DataFreshness";
import { SearchVisibility } from "@/components/SearchVisibility";
import { ApiError, apiFetch } from "@/lib/api";
import { presets } from "@/lib/bi";
import { getClients } from "@/lib/clients";
import type { Sv } from "@/lib/search-visibility";

export const metadata = { title: "Search visibility" };

const DATE = /^\d{4}-\d{2}-\d{2}$/;

export default async function SearchVisibilityPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<{ from?: string; to?: string; bucket?: string }>;
}) {
  const { clientSlug } = await params;
  const { from, to, bucket } = await searchParams;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  // Search Console runs about three days behind, so the default is the 90 days ending then.
  const ranges = presets();
  const fallback = ranges.find((r) => r.key === "90") ?? ranges[0];
  const start = from && DATE.test(from) ? from : fallback.from;
  const end = to && DATE.test(to) ? to : fallback.to;

  let data: Sv | null = null;
  let error: string | null = null;
  try {
    const q = new URLSearchParams({ from: start, to: end });
    if (bucket) q.set("bucket", bucket);
    data = await apiFetch<Sv>(`/v2/search-visibility?${q}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "Search visibility could not be built: the API did not answer.";
  }

  return (
    <>
      <DataFreshness clientId={client.id} />
      <SearchVisibility client={client} from={start} to={end} bucket={bucket ?? ""} data={data} error={error} />
    </>
  );
}
