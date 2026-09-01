import { notFound } from "next/navigation";

import { ClientWorkspaceNav } from "@/components/ClientWorkspaceNav";
import { ConversionDefinitionsPanel } from "@/components/ConversionDefinitionsPanel";
import { apiFetch, type ConversionDefinition } from "@/lib/api";
import { loadClientById } from "@/lib/context";

export default async function ClientConversionsPage({
  params,
}: {
  params: Promise<{ clientId: string }>;
}) {
  const { clientId } = await params;
  const client = await loadClientById(clientId);
  if (!client) notFound();

  let conversions: ConversionDefinition[] = [];
  let error: string | null = null;

  try {
    conversions = await apiFetch<ConversionDefinition[]>("/admin/conversion-definitions", {
      clientId,
    });
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load conversions";
  }

  return (
    <section>
      <ClientWorkspaceNav clientId={clientId} active={`/clients/${clientId}/conversions`} />
      <h1 className="text-2xl font-semibold">Conversions</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Define which GA4 events count as leads for {client.client_name}. Dashboard conversion KPIs
        use only active lead definitions here.
      </p>

      {error ? (
        <p className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          {error}
        </p>
      ) : null}

      <div className="mt-6">
        <ConversionDefinitionsPanel clientId={clientId} conversions={conversions} />
      </div>
    </section>
  );
}
