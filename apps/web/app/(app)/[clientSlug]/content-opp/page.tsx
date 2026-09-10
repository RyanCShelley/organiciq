import { SearchOpportunitiesTable } from "@/components/DecisionEngine/SearchOpportunitiesTable";
import { Alert } from "@/components/ui/Alert";
import { apiFetch } from "@/lib/api";
import { requireAccountClient } from "@/lib/account-routes.server";
import { resolveDateRange } from "@/lib/context";
import {
  normalizeDiagnoseResponse,
  type DiagnoseResponse,
  type SearchOpportunity,
} from "@/lib/decision-engine";

export default async function ContentOppPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clientSlug } = await params;
  const query = await searchParams;
  const client = await requireAccountClient(clientSlug, "content-opp");
  const clientId = client.id;
  const { from, to } = await resolveDateRange(query);

  let contentOpps: SearchOpportunity[] = [];
  let error: string | null = null;

  try {
    const diagnose = normalizeDiagnoseResponse(
      await apiFetch<DiagnoseResponse>(
        `/decisions/diagnose?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        { clientId },
      ),
    );
    contentOpps = diagnose.search_opportunities ?? [];
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load Content Opp";
  }

  return (
    <section>
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <section className="workspace-section">
        {!error && contentOpps.length === 0 ? (
          <Alert variant="info">
            No Content Opp rows for this period. Confirm GSC is synced and Decision Engine is ready.
          </Alert>
        ) : null}
        {contentOpps.length > 0 ? (
          <SearchOpportunitiesTable
            items={contentOpps}
            title="Content Opp"
            description="Top opportunities by impressions. Use search to find a page, or load 25 more."
          />
        ) : null}
      </section>
    </section>
  );
}
