import { notFound } from "next/navigation";

import { ConversionEvents, ConversionPages } from "@/components/ConversionsPanel";
import { apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import type { ConversionPage, EventCandidate } from "@/lib/conversions";

export const metadata = { title: "Settings · Conversions & Goals" };

export default async function ConversionsPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  const [events, pages] = await Promise.all([
    apiFetch<EventCandidate[]>("/admin/conversion-definitions/ga4-events", { clientId: client.id }),
    apiFetch<ConversionPage[]>("/admin/conversion-pages", { clientId: client.id }),
  ]);

  return (
    <div className="space-y-6">
      <ConversionEvents clientId={client.id} slug={client.slug} events={events} />
      <ConversionPages clientId={client.id} slug={client.slug} pages={pages} />
    </div>
  );
}
