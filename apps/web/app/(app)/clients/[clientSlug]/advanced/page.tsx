import { ClientAccountSection } from "@/components/ClientAccountSection";
import { ExcludedPagesPanel, type ExcludedPage } from "@/components/ExcludedPagesPanel";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch } from "@/lib/api";
import { requireWorkspaceClient } from "@/lib/context";
export default async function AdvancedPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = await requireWorkspaceClient(clientSlug, "advanced");
  let excluded: ExcludedPage[] | null = null;
  try { excluded = await apiFetch<ExcludedPage[]>("/decisions/excluded-pages", { clientId: client.id }); } catch { /* Do not present an empty editable list on failure. */ }
  return <div className="space-y-6"><ClientAccountSection client={client} section="advanced" /><section className="workspace-section"><SectionHeader title="Pages the engine leaves alone" description="Exclude pages or sections from new growth-action recommendations." /><div className="workspace-panel">{excluded ? <ExcludedPagesPanel clientId={client.id} initial={excluded} /> : <Alert variant="danger">Exclusions could not be loaded. Reload before editing.</Alert>}</div></section></div>;
}
