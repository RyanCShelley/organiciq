import { ClientMappingContent } from "@/components/ClientMappingSection";
import { requireWorkspaceClient } from "@/lib/context";
export default async function KeywordMapPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = await requireWorkspaceClient(clientSlug, "keyword-map");
  return <ClientMappingContent client={client} />;
}
