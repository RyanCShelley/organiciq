import { notFound } from "next/navigation";

import { BusinessIntelligence } from "@/components/BusinessIntelligence";
import { ApiError, apiFetch } from "@/lib/api";
import type { AdsSummary } from "@/lib/ads";
import { presets, type Bi } from "@/lib/bi";
import { findClient } from "@/lib/clients";
import { lastCompleteMonth } from "@/lib/review";

export const metadata = { title: "OrganicIQ insights" };

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
  const client = await findClient(clientSlug);
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
    error = e instanceof ApiError ? e.message : "OrganicIQ insights could not be built: the API did not answer.";
  }

  // Paid ads sit beside the organic picture for clients on Ads Accelerator. If they cannot be read, the rest of the page still shows.
  const adsMonth = lastCompleteMonth();
  const ads = client.service_reporting?.ad_accelerator ? await apiFetch<AdsSummary>(`/v2/ads/summary?month=${adsMonth}`, { clientId: client.id }).catch(() => null) : null;

  return (
    <>
      <BusinessIntelligence client={client} from={start} to={end} channel={channel ?? ""} data={data} error={error} ads={ads} />
    </>
  );
}
