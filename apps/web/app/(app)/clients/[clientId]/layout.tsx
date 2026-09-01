import { notFound } from "next/navigation";

import { ClientWorkspaceHeader } from "@/components/ClientWorkspaceNav";
import { loadClientById } from "@/lib/context";

export default async function ClientWorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ clientId: string }>;
}) {
  const { clientId } = await params;
  const client = await loadClientById(clientId);
  if (!client) notFound();

  return (
    <div>
      <ClientWorkspaceHeader clientName={client.client_name} domain={client.domain} />
      {children}
    </div>
  );
}
