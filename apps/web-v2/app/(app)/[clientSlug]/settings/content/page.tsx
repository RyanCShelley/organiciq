import { notFound } from "next/navigation";

import { FeedSettings } from "@/components/FeedSettings";
import { SitemapForm } from "@/components/ClientForms";
import { apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import type { ClientFeed } from "@/lib/feeds";

export const metadata = { title: "Settings · Content sources" };

export default async function ContentSourcesPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();
  const feeds = await apiFetch<ClientFeed[]>("/v2/feeds", { clientId: client.id });
  return (
    <div className="space-y-6">
      <SitemapForm client={client} />
      <FeedSettings clientId={client.id} slug={client.slug} feeds={feeds} />
    </div>
  );
}
