import { notFound } from "next/navigation";

import { BusinessIntelligence } from "@/components/BusinessIntelligence";
import { DataFreshness } from "@/components/DataFreshness";
import { ApiError, apiFetch } from "@/lib/api";
import { presets, type AskInfo, type Bi } from "@/lib/bi";
import { getClients } from "@/lib/clients";

export const metadata = { title: "Business Intelligence" };

const DATE = /^\d{4}-\d{2}-\d{2}$/;

export default async function BusinessIntelligencePage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<{ from?: string; to?: string; channel?: string }>;
}) {
  const { clientSlug } = await params;
  const { from, to, channel } = await searchParams;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  const first = presets()[0];
  const start = from && DATE.test(from) ? from : first.from;
  const end = to && DATE.test(to) ? to : first.to;

  let data: Bi | null = null;
  let error: string | null = null;
  try {
    const q = new URLSearchParams({ from: start, to: end });
    if (channel) q.set("channel", channel);
    data = await apiFetch<Bi>(`/v2/bi?${q}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "Business Intelligence could not be built: the API did not answer.";
  }

  // Questions are optional: without them the screen still works.
  const ask = await apiFetch<AskInfo>("/v2/ask", { clientId: client.id }).catch(() => null);

  return (
    <>
      <DataFreshness clientId={client.id} />
      <BusinessIntelligence client={client} from={start} to={end} channel={channel ?? ""} data={data} error={error} ask={ask} />
    </>
  );
}
