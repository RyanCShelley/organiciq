import { ClientWorkspaceNav } from "@/components/ClientWorkspaceNav";
import { DataTable } from "@/components/analytics/DataTable";
import { StatusBadge } from "@/components/analytics/StatusBadge";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Ga4ConnectPanel } from "@/components/Ga4ConnectPanel";
import { GscConnectPanel } from "@/components/GscConnectPanel";
import { SeRankingConnectPanel } from "@/components/SeRankingConnectPanel";
import { SyncAll90DaysPanel } from "@/components/SyncAll90DaysPanel";
import { apiFetch, type Integration } from "@/lib/api";
import { clientHref } from "@/lib/client-path";
import { requireWorkspaceClient } from "@/lib/context";

export default async function ClientIntegrationsPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clientSlug } = await params;
  const query = await searchParams;
  const client = await requireWorkspaceClient(clientSlug, "integrations");
  const clientId = client.id;

  const oauth = typeof query.oauth === "string" ? query.oauth : null;
  const oauthMessage = typeof query.message === "string" ? query.message : null;

  let rows: Integration[] = [];
  let error: string | null = null;

  try {
    rows = await apiFetch<Integration[]>("/integrations", { clientId });
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load integrations";
  }

  const gsc = rows.find((row) => row.provider === "gsc");
  const ga4 = rows.find((row) => row.provider === "ga4");
  const ser = rows.find((row) => row.provider === "se_ranking");

  return (
    <section>
      <ClientWorkspaceNav clientSlug={client.slug} active={clientHref(client.slug, "integrations")} />

      {oauth === "connected" ? (
        <Alert variant="success" className="mb-4">
          Google connected for all clients. Load properties and select a GSC site and a GA4 property
          for {client.client_name}.
        </Alert>
      ) : null}
      {oauth === "error" ? (
        <Alert variant="danger" className="mb-4">
          OAuth failed{oauthMessage ? `: ${oauthMessage}` : ""}
        </Alert>
      ) : null}
      {error ? (
        <Alert variant="danger" className="mb-4">
          {error}
        </Alert>
      ) : null}

      <section className="workspace-section">
        <SectionHeader
          title="Property mapping"
          description="Connect each source, confirm it shows connected with a property, then run one Sync 90 days for this client."
        />
        <DataTable
          columns={[
            {
              key: "provider",
              header: "Provider",
              render: (row) => (
                <span className="font-medium uppercase">{row.provider.replaceAll("_", " ")}</span>
              ),
            },
            {
              key: "status",
              header: "Status",
              render: (row) => (
                <StatusBadge
                  available={row.connection_status === "connected"}
                  availableLabel={formatStatus(row.connection_status)}
                  unavailableLabel={formatStatus(row.connection_status)}
                />
              ),
            },
            {
              key: "property",
              header: "Property",
              render: (row) =>
                row.external_property_id ? (
                  <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--text-secondary)]">
                    {row.external_property_id}
                    {row.provider === "gsc" && (row.gsc_secondary_site_urls?.length ?? 0) > 0
                      ? ` (+${row.gsc_secondary_site_urls!.length} secondary)`
                      : ""}
                  </span>
                ) : (
                  <span className="text-[var(--text-tertiary)]">—</span>
                ),
            },
            {
              key: "last_sync",
              header: "Last sync",
              render: (row) => (
                <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--text-secondary)]">
                  {row.last_successful_sync ?? "—"}
                </span>
              ),
            },
          ]}
          rows={rows}
          getRowKey={(row) => row.id}
          emptyMessage="No integrations configured yet."
        />
      </section>

      <GscConnectPanel
        clientId={clientId}
        connected={gsc?.connection_status === "connected"}
        propertyId={gsc?.external_property_id ?? null}
        secondarySiteUrls={gsc?.gsc_secondary_site_urls ?? []}
      />
      <Ga4ConnectPanel
        clientId={clientId}
        connected={ga4?.connection_status === "connected"}
        propertyId={ga4?.external_property_id ?? null}
      />
      <SeRankingConnectPanel
        clientId={clientId}
        connected={ser?.connection_status === "connected"}
        propertyId={ser?.external_property_id ?? null}
        projectName={ser?.external_account_id ?? null}
      />
      <SyncAll90DaysPanel
        clientId={clientId}
        hasGscProperty={Boolean(gsc?.external_property_id)}
        hasGa4Property={Boolean(ga4?.external_property_id)}
        hasSerankingProject={Boolean(ser?.external_property_id)}
      />
    </section>
  );
}

function formatStatus(status: string): string {
  if (status === "not_connected") return "Not Connected";
  return status.replaceAll("_", " ");
}
