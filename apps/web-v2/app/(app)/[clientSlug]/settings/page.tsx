import { notFound } from "next/navigation";

import { FeedSettings } from "@/components/FeedSettings";
import { apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import type { ClientFeed } from "@/lib/feeds";

export const metadata = { title: "Settings" };

export default async function SettingsPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  const feeds = await apiFetch<ClientFeed[]>("/v2/feeds", { clientId: client.id });

  return (
    <section className="max-w-3xl space-y-8">
      <header>
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">Settings</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">{client.client_name}</p>
      </header>
      <FeedSettings clientId={client.id} slug={client.slug} feeds={feeds} />
    </section>
  );
}
