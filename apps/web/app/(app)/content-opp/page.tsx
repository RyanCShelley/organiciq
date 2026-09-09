import { SearchOpportunitiesTable } from "@/components/DecisionEngine/SearchOpportunitiesTable";
import { Alert } from "@/components/ui/Alert";
import { PageHeader } from "@/components/ui/PageHeader";
import { apiFetch } from "@/lib/api";
import { resolveClientId, resolveDateRange } from "@/lib/context";
import {
  normalizeDiagnoseResponse,
  type DiagnoseResponse,
  type SearchOpportunity,
} from "@/lib/decision-engine";

export default async function ContentOppPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const clientId = await resolveClientId(params);
  const { from, to } = await resolveDateRange(params);

  let contentOpps: SearchOpportunity[] = [];
  let error: string | null = null;

  if (!clientId) {
    error = "Select a client to view Content Opp.";
  } else {
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
  }

  return (
    <section>
      <PageHeader
        title="Content Opp"
        description="Striking-distance content opportunities from Search Console for strategist review."
        meta={
          <span>
            Period: <strong className="text-[var(--text-primary)]">{from}</strong> to{" "}
            <strong className="text-[var(--text-primary)]">{to}</strong>
          </span>
        }
      />

      {error ? <Alert variant="danger" className="mt-4">{error}</Alert> : null}

      <section className="mt-4 workspace-section">
        {!error && contentOpps.length === 0 ? (
          <Alert variant="info">
            No Content Opp rows for this period. Confirm GSC is synced and Decision Engine is ready.
          </Alert>
        ) : null}
        {contentOpps.length > 0 ? (
          <SearchOpportunitiesTable
            items={contentOpps}
            title="Content Opp"
            description="Striking-distance rankings for content planning."
          />
        ) : null}
      </section>
    </section>
  );
}
