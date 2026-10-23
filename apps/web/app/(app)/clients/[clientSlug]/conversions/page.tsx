import { ClientConversionsContent } from "@/components/ClientConversionsSection";
import { requireWorkspaceClient } from "@/lib/context";
export default async function ClientConversionsPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = await requireWorkspaceClient(clientSlug, "conversions");
  return <ClientConversionsContent client={client} />;
}
