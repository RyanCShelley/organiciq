import { ClientConnections } from "@/components/ClientConnectionsSection";
import { requireWorkspaceClient } from "@/lib/context";
import { Alert } from "@/components/ui/Alert";
export default async function ClientIntegrationsPage({ params, searchParams }: { params: Promise<{ clientSlug: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { clientSlug } = await params; const query = await searchParams;
  const client = await requireWorkspaceClient(clientSlug, "integrations");
  return <><div role="status">{query.oauth === "connected" ? <Alert variant="success">Google connected. Select this client’s GA4 and Search Console properties below.</Alert> : query.oauth === "error" ? <Alert variant="danger">Google could not connect. Try again or review access in Platform Settings.</Alert> : null}</div><ClientConnections client={client} /></>;
}
