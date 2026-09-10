import { ClientWorkspaceNav } from "@/components/ClientWorkspaceNav";
import { ConversionDefinitionsPanel } from "@/components/ConversionDefinitionsPanel";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch, type ConversionDefinition } from "@/lib/api";
import { clientHref } from "@/lib/client-path";
import { requireWorkspaceClient } from "@/lib/context";

export default async function ClientConversionsPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = await requireWorkspaceClient(clientSlug, "conversions");
  const clientId = client.id;

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
      <ClientWorkspaceNav clientSlug={client.slug} active={clientHref(client.slug, "conversions")} />

      {error ? (
        <Alert variant="danger" className="mb-4">
          {error}
        </Alert>
      ) : null}

      <section className="workspace-section">
        <SectionHeader
          title="Lead definitions"
          description={`Which GA4 events count as leads for ${client.client_name}. Dashboard conversion KPIs use only active lead definitions here.`}
        />
        <div className="workspace-panel">
          <ConversionDefinitionsPanel clientId={clientId} conversions={conversions} />
        </div>
      </section>
    </section>
  );
}
