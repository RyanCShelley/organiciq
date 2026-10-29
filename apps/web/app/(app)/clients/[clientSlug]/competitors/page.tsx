import { ClientAccountSection } from "@/components/ClientAccountSection";
import { requireWorkspaceClient } from "@/lib/context";
export default async function CompetitorsPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = await requireWorkspaceClient(clientSlug, "competitors");
  return <ClientAccountSection client={client} section="competitors" />;
}
