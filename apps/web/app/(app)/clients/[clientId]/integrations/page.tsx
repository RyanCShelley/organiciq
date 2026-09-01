import { notFound } from "next/navigation";

import { ClientWorkspaceNav } from "@/components/ClientWorkspaceNav";
import { Ga4ConnectPanel } from "@/components/Ga4ConnectPanel";
import { GscConnectPanel } from "@/components/GscConnectPanel";
import { SeRankingConnectPanel } from "@/components/SeRankingConnectPanel";
import { SyncAll90DaysPanel } from "@/components/SyncAll90DaysPanel";
import { apiFetch, type Integration } from "@/lib/api";
import { loadClientById } from "@/lib/context";

export default async function ClientIntegrationsPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clientId } = await params;
  const query = await searchParams;
  const client = await loadClientById(clientId);
  if (!client) notFound();

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
      <ClientWorkspaceNav clientId={clientId} active={`/clients/${clientId}/integrations`} />
      <h1 className="text-2xl font-semibold">Integrations</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Connect Google Data OAuth for Search Console and Analytics, then map properties for{" "}
        {client.client_name}. SE Ranking uses an account API key.
      </p>

      {oauth === "connected" ? (
        <p className="mt-4 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100">
          Google connected. Load properties and select a GSC site and a GA4 property.
        </p>
      ) : null}
      {oauth === "error" ? (
        <p className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          OAuth failed{oauthMessage ? `: ${oauthMessage}` : ""}
        </p>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
          {error}
        </p>
      ) : null}

      <div className="mt-6 overflow-x-auto rounded-xl border border-[var(--border)]">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-white/5 text-[var(--muted)]">
            <tr>
              <th className="px-4 py-3 font-medium">Provider</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Property</th>
              <th className="px-4 py-3 font-medium">Last sync</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-[var(--border)]">
                <td className="px-4 py-3 uppercase">{row.provider}</td>
                <td className="px-4 py-3">{formatStatus(row.connection_status)}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{row.external_property_id ?? "—"}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{row.last_successful_sync ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <GscConnectPanel
        clientId={clientId}
        connected={gsc?.connection_status === "connected"}
        propertyId={gsc?.external_property_id ?? null}
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
