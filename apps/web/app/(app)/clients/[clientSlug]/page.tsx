import Link from "next/link";

import { StatusBadge } from "@/components/analytics/StatusBadge";
import { ClientSettingsForm } from "@/components/ClientSettingsForm";
import { ClientWorkspaceNav } from "@/components/ClientWorkspaceNav";
import { ConversionDefinitionsPanel } from "@/components/ConversionDefinitionsPanel";
import { Alert } from "@/components/ui/Alert";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
import {
  apiFetch,
  type Client,
  type ConversionDefinition,
  type DataHealthRow,
  type Tier,
} from "@/lib/api";
import { clientHref } from "@/lib/client-path";
import { requireWorkspaceClient } from "@/lib/context";

export default async function ClientSettingsPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = await requireWorkspaceClient(clientSlug);
  const clientId = client.id;

  let tiers: Tier[] = [];
  let health: DataHealthRow[] = [];
  let conversions: ConversionDefinition[] = [];
  let loadError: string | null = null;

  try {
    const [tierRows, healthRows, conversionRows, freshClient] = await Promise.all([
      apiFetch<Tier[]>("/admin/tiers"),
      apiFetch<DataHealthRow[]>("/admin/data-health", { clientId }),
      apiFetch<ConversionDefinition[]>("/admin/conversion-definitions", { clientId }),
      apiFetch<Client>(`/clients/${clientId}`, { clientId }),
    ]);
    tiers = tierRows;
    health = healthRows;
    conversions = conversionRows;
    Object.assign(client, freshClient);
  } catch (e) {
    loadError = e instanceof Error ? e.message : "Failed to load client settings";
  }

  const hasLeadConversions = conversions.some(
    (row) => row.active && row.conversion_type === "lead",
  );
  const healthy = health.filter((row) => row.status === "Healthy").length;

  return (
    <section>
      <ClientWorkspaceNav clientSlug={client.slug} active={clientHref(client.slug)} />
      <PageHeader
        title="Client settings"
        description="Account record for tier allowances, contract date, lead goal, conversions, and strategy sheet."
      />

      {loadError ? <Alert variant="danger">{loadError}</Alert> : null}

      <div className="mt-4 space-y-[var(--section-gap)]">
        <section className="workspace-section">
          <SectionHeader title="Account record" description="Core fields for this Organic IQ client." />
          <div className="workspace-panel">
            <ClientSettingsForm
              client={client}
              tiers={tiers}
              hasLeadConversions={hasLeadConversions}
            />
          </div>
        </section>

        <section className="workspace-section">
          <SectionHeader
            title="Conversions"
            description="Add or remove GA4 lead events used by Dashboard and Decision Engine."
            actions={
              <Link href={clientHref(client.slug, "conversions")} className="btn btn-ghost btn-sm">
                Open conversions page
              </Link>
            }
          />
          <div className="workspace-panel">
            <ConversionDefinitionsPanel clientId={clientId} conversions={conversions} />
          </div>
        </section>

        <section className="workspace-section">
          <SectionHeader
            title="Data freshness"
            description="Source health for this account. Moved off the Dashboard into the client record."
            actions={
              <Link href={clientHref(client.slug, "data-health")} className="btn btn-ghost btn-sm">
                Open data health
              </Link>
            }
          />
          <div className="workspace-panel space-y-3">
            <p className="text-sm text-[var(--text-secondary)]">
              {healthy}/{health.length || 0} sources healthy
            </p>
            {health.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="text-[var(--text-tertiary)]">
                    <tr>
                      <th className="py-2 pr-4 font-medium">Source</th>
                      <th className="py-2 pr-4 font-medium">Status</th>
                      <th className="py-2 font-medium">Fact through</th>
                    </tr>
                  </thead>
                  <tbody>
                    {health.map((row) => (
                      <tr key={row.source} className="border-t border-[var(--border)]">
                        <td className="py-2 pr-4">{row.source.replaceAll("_", " ")}</td>
                        <td className="py-2 pr-4">
                          <StatusBadge available={row.status === "Healthy"} />
                        </td>
                        <td className="py-2 text-[var(--text-secondary)]">
                          {row.fact_through ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-[var(--text-tertiary)]">No watermark data yet.</p>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
