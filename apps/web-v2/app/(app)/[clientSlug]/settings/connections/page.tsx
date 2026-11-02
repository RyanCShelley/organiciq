import { notFound } from "next/navigation";

import { ConnectionsPanel } from "@/components/Connections";
import { apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import type { Connections, IntegrationRow } from "@/lib/connections";

export const metadata = { title: "Settings · Connections" };

export default async function ConnectionsPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<{ oauth?: string; message?: string }>;
}) {
  const { clientSlug } = await params;
  const { oauth, message } = await searchParams;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  const [integrations, connections, me] = await Promise.all([
    apiFetch<IntegrationRow[]>("/integrations", { clientId: client.id }),
    apiFetch<Connections>("/v2/connections", { clientId: client.id }),
    apiFetch<{ role: string }>("/auth/me").catch(() => null),
  ]);

  return (
    <ConnectionsPanel
      client={client}
      integrations={integrations}
      connections={connections}
      isAdmin={me?.role === "sma_admin"}
      oauth={oauth ? { status: oauth, message } : undefined}
    />
  );
}
