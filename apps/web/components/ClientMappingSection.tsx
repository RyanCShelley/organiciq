import { PagesKeywordsWorkspace } from "@/components/PagesKeywordsWorkspace";
import type { KeywordMapRow } from "@/components/DecisionEngine/KeywordPageMapTable";
import type { PageStagePayload } from "@/components/PageStagesPanel";
import type { ConversionPage } from "@/components/ConversionPagesPanel";
import { apiFetch, type Client } from "@/lib/api";
export async function ClientMappingContent({ client }: { client: Client }) {
  const [map, stages, conversions] = await Promise.allSettled([
    apiFetch<{ keywords: KeywordMapRow[]; pages: string[] }>("/decisions/keyword-page-map", { clientId: client.id }),
    apiFetch<PageStagePayload>("/decisions/page-stages", { clientId: client.id }),
    apiFetch<ConversionPage[]>("/admin/conversion-pages", { clientId: client.id }),
  ]);
  const errors = [map.status === "rejected" ? "Keyword ownership could not be loaded. Reload before editing it." : "", stages.status === "rejected" ? "Page stages could not be loaded." : "", conversions.status === "rejected" ? "Conversion destinations could not be loaded." : ""].filter(Boolean);
  return <PagesKeywordsWorkspace clientId={client.id} slug={client.slug} keywords={map.status === "fulfilled" ? map.value.keywords : []} pages={map.status === "fulfilled" ? map.value.pages : []} stages={stages.status === "fulfilled" ? stages.value : null} conversions={conversions.status === "fulfilled" ? conversions.value : []} errors={errors} />;
}
