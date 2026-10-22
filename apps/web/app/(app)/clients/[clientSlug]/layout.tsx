import { notFound } from "next/navigation";

import { ClientWorkspaceHeader, ClientSettingsShell } from "@/components/ClientWorkspaceNav";
import { loadClientByParam } from "@/lib/context";

export default async function ClientWorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = await loadClientByParam(clientSlug);
  if (!client) notFound();

  return (
    <div>
      <ClientWorkspaceHeader clientName={client.client_name} domain={client.domain} />
      <ClientSettingsShell clientSlug={client.slug}>{children}</ClientSettingsShell>
    </div>
  );
}
