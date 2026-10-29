import { ClientAccountSection } from "@/components/ClientAccountSection";
import { Alert } from "@/components/ui/Alert";
import { Ga4ConnectPanel } from "@/components/Ga4ConnectPanel";
import { GscConnectPanel } from "@/components/GscConnectPanel";
import { SeRankingConnectPanel } from "@/components/SeRankingConnectPanel";
import { SyncAll90DaysPanel } from "@/components/SyncAll90DaysPanel";
import { apiFetch, type Client, type Integration } from "@/lib/api";

export async function ClientConnections({ client, showSync = true }: { client: Client; showSync?: boolean }) {
  let rows: Integration[];
  try { rows = await apiFetch<Integration[]>("/integrations", { clientId: client.id }); } catch { return <Alert variant="danger">Connections could not be loaded. Reload before changing properties.</Alert>; }
  const gsc = rows.find(r => r.provider === "gsc"), ga4 = rows.find(r => r.provider === "ga4"), ser = rows.find(r => r.provider === "se_ranking");
  return <div className="space-y-5"><div><h2 className="section-title">Connections</h2><p className="section-description">Connect Google once, then select this client’s properties. Saving a property starts its 90-day reporting sync. Routine syncs continue automatically.</p></div>
    <Ga4ConnectPanel clientId={client.id} connected={ga4?.connection_status === "connected"} propertyId={ga4?.external_property_id ?? null} />
    <GscConnectPanel clientId={client.id} connected={gsc?.connection_status === "connected"} propertyId={gsc?.external_property_id ?? null} secondarySiteUrls={gsc?.gsc_secondary_site_urls ?? []} />
    <SeRankingConnectPanel clientId={client.id} connected={ser?.connection_status === "connected"} propertyId={ser?.external_property_id ?? null} projectName={ser?.external_account_id ?? null} />
    <ClientAccountSection client={client} section="connections" />
    {showSync ? <SyncAll90DaysPanel clientId={client.id} hasGscProperty={Boolean(gsc?.external_property_id)} hasGa4Property={Boolean(ga4?.external_property_id)} hasSerankingProject={Boolean(ser?.external_property_id)} hasDomain={Boolean(client.domain)} compact /> : null}
  </div>;
}
