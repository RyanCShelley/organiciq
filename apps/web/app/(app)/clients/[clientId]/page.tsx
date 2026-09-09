import Link from "next/link";
import { notFound } from "next/navigation";

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
import { loadClientById } from "@/lib/context";

export default async function ClientSettingsPage({
  params,
}: {
  params: Promise<{ clientId: string }>;
}) {
  const { clientId } = await params;
  const client = await loadClientById(clientId);
  if (!client) notFound();

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
      <ClientWorkspaceNav clientId={clientId} active={`/clients/${clientId}`} />
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
              <Link href={`/clients/${clientId}/conversions`} className="btn btn-ghost btn-sm">
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
              <Link href={`/clients/${clientId}/data-health`} className="btn btn-ghost btn-sm">
                Open data health
              </Link>
            }
          />
          <div className="workspace-panel">
            <p className="text-sm text-[var(--text-secondary)]">
              {healthy}/{health.length || 0} sources healthy
            </p>
            {health.length > 0 ? (
              <ul className="mt-3 divide-y divide-[var(--border)]">
                {health.map((row) => (
                  <li
                    key={row.source}
                    className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
                  >
                    <span className="font-medium">{row.source.replaceAll("_", " ")}</span>
                    <StatusBadge
                      available={row.status === "Healthy"}
                      availableLabel={row.status}
                      unavailableLabel={row.status}
                    />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-[var(--text-tertiary)]">No freshness rows yet.</p>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
