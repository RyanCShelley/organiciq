import Link from "next/link";
import { ClientGoalsSection } from "@/components/ClientGoalsSection";
import { ConversionDefinitionsPanel } from "@/components/ConversionDefinitionsPanel";
import { ConversionPagesPanel, type ConversionPage } from "@/components/ConversionPagesPanel";
import type { SetupState } from "@/components/SetupChecklist";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch, type Client, type ConversionDefinition } from "@/lib/api";
import { clientHref } from "@/lib/client-path";

export async function ClientConversionsContent({ client, includeGoals = true }: { client: Client; includeGoals?: boolean }) {
  const results = await Promise.allSettled([
    apiFetch<ConversionDefinition[]>("/admin/conversion-definitions", { clientId: client.id }),
    apiFetch<ConversionPage[]>("/admin/conversion-pages", { clientId: client.id }),
    apiFetch<SetupState>(`/clients/${client.id}/setup`, { clientId: client.id }),
  ]);
  const [definitions, pages, setup] = results;
  const ga4Ready = setup.status === "fulfilled" && setup.value.steps.find(s => s.key === "leads")?.blocked_by == null;
  return <div className="space-y-6">
    <section className="workspace-section"><SectionHeader title="Lead definitions" description="Select the GA4 events that count as leads once. Reporting, the growth engine and new baseline calculations use these saved definitions." /><div className="workspace-panel">{definitions.status === "rejected" ? <Alert variant="danger">Lead definitions could not be loaded. Reload before editing.</Alert> : ga4Ready ? <ConversionDefinitionsPanel clientId={client.id} conversions={definitions.value} /> : <Alert variant="warning">Connect GA4 and complete its initial sync before selecting lead events. <Link className="underline" href={clientHref(client.slug, "integrations")}>Open Connections</Link></Alert>}</div></section>
    <section className="workspace-section"><SectionHeader title="Conversion pages" description="Declare the pages where a visitor can take the next step. Page stages and keyword ownership live together in Pages & Keywords." /><div className="workspace-panel">{pages.status === "fulfilled" ? <ConversionPagesPanel clientId={client.id} initial={pages.value} /> : <Alert variant="danger">Conversion pages could not be loaded. Reload before editing.</Alert>}</div></section>
    {includeGoals ? <ClientGoalsSection client={client} definitionKey={definitions.status === "fulfilled" ? JSON.stringify(definitions.value) : "unavailable"} /> : null}
  </div>;
}
