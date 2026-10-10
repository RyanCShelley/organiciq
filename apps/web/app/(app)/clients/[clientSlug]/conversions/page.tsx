import { ClientWorkspaceNav } from "@/components/ClientWorkspaceNav";
import { ConversionDefinitionsPanel } from "@/components/ConversionDefinitionsPanel";
import {
  ConversionPagesPanel,
  type ConversionPage,
} from "@/components/ConversionPagesPanel";
import {
  PageStagesPanel,
  type PageStagePayload,
} from "@/components/PageStagesPanel";
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
  let conversionPages: ConversionPage[] = [];
  let pageStages: PageStagePayload | null = null;
  let error: string | null = null;
  let stagesError: string | null = null;

  try {
    [conversions, conversionPages] = await Promise.all([
      apiFetch<ConversionDefinition[]>("/admin/conversion-definitions", { clientId }),
      apiFetch<ConversionPage[]>("/admin/conversion-pages", { clientId }),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load conversions";
  }

  // Fetched on its own. Sharing a Promise.all with the two panels above meant
  // one failing call took down all three and removed this section from the
  // page without saying anything — a section that vanishes silently is
  // indistinguishable from one that was never deployed.
  try {
    pageStages = await apiFetch<PageStagePayload>("/decisions/page-stages", {
      clientId,
    });
  } catch (e) {
    stagesError = e instanceof Error ? e.message : "Failed to load page stages";
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

      <section className="workspace-section">
        <SectionHeader
          title="Conversion pages"
          description="Where a visitor is meant to end up. Without these the engine guesses from the URL — /contact, /demo, /quote — which sent one client's team to a page that does not exist."
        />
        <div className="workspace-panel">
          <ConversionPagesPanel clientId={clientId} initial={conversionPages} />
        </div>
      </section>

      <section className="workspace-section">
        <SectionHeader
          title="Page stages"
          description="Where the reader of each landing page is: learning, comparing, or ready to buy. A model reads the page and proposes; the engine reads only what you confirm. This is what the next-step test needs to tell a dead end from a page that is doing its job."
        />
        <div className="workspace-panel">
          {pageStages ? (
            <PageStagesPanel clientId={clientId} initial={pageStages} />
          ) : (
            <Alert variant="danger">
              {stagesError ?? "Page stages could not be loaded."}
            </Alert>
          )}
        </div>
      </section>
    </section>
  );
}
