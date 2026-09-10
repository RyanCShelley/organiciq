import Link from "next/link";

import { FindingsReviewPanel } from "@/components/DecisionEngine/FindingsReviewPanel";
import { GrowthActionFilter } from "@/components/DecisionEngine/GrowthActionFilter";
import { GrowthActionGrid } from "@/components/DecisionEngine/GrowthActionGrid";
import { RecommendedActionCard } from "@/components/DecisionEngine/RecommendedActionCard";
import { RunEngineButton } from "@/components/DecisionEngine/RunEngineButton";
import { SummaryStrip } from "@/components/DecisionEngine/SummaryStrip";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch, type Client, type Tier } from "@/lib/api";
import { accountToolHref } from "@/lib/account-routes";
import { requireAccountClient } from "@/lib/account-routes.server";
import { resolveDateRange } from "@/lib/context";
import {
  applySuggestedAlternatives,
  countSelectedTowardPlan,
  normalizeDiagnoseResponse,
  type DiagnoseResponse,
  type Finding,
  type StoredDecision,
} from "@/lib/decision-engine";
import { resolvePlanAllowances } from "@/lib/plan-allowances";
import { withNavContext } from "@/lib/navigation";

function readinessLabel(key: string): string {
  if (key === "search_console") return "Search Console";
  if (key === "crawl_audit") return "Crawl / Audit";
  return key;
}

export default async function DecisionEnginePage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clientSlug } = await params;
  const query = await searchParams;
  const selectedClient = await requireAccountClient(clientSlug, "decision-engine");
  const clientId = selectedClient.id;
  const { from, to } = await resolveDateRange(query);
  const leverFilter =
    typeof query.lever === "string" && query.lever.length > 0 ? query.lever : "all";

  let data: DiagnoseResponse | null = null;
  let decisions: StoredDecision[] = [];
  let growthPlanAllowance = 0;
  let error: string | null = null;

  try {
    const [diagnose, stored, client, tiers] = await Promise.all([
      apiFetch<DiagnoseResponse>(
        `/decisions/diagnose?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        { clientId },
      ),
      apiFetch<StoredDecision[]>(
        `/decisions?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        { clientId },
      ).catch(() => [] as StoredDecision[]),
      apiFetch<Client>(`/clients/${clientId}`, { clientId }),
      apiFetch<Tier[]>("/admin/tiers"),
    ]);
    data = normalizeDiagnoseResponse(diagnose);
    decisions = stored;
    const tier = tiers.find((row) => row.id === client.tier_id);
    growthPlanAllowance = resolvePlanAllowances(client, tier).growthActionAllowance;
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load Decision Engine";
  }

  const allFindings: Finding[] = data?.findings ?? [];
  const additionalFindings = allFindings.filter((finding) => !finding.is_recommended_action);
  const searchOpportunities = data?.search_opportunities ?? [];
  const recommendations = data?.recommended_actions ?? [];
  const suggestions = applySuggestedAlternatives(
    recommendations,
    additionalFindings,
    growthPlanAllowance,
  );
  const recommendedKeys = new Set(recommendations.map((item) => item.rule_key));
  const suggestedKeys = new Set(suggestions.map((item) => item.rule_key));
  const filteredRecommendations =
    leverFilter === "all"
      ? recommendations
      : recommendations.filter((item) => item.lever === leverFilter);
  const filteredSuggestions =
    leverFilter === "all"
      ? suggestions
      : suggestions.filter((item) => item.lever === leverFilter);
  const filteredFindings =
    leverFilter === "all" ? allFindings : allFindings.filter((item) => item.lever === leverFilter);
  const decisionByRule = new Map(decisions.map((row) => [row.rule_key, row]));
  const selectedTowardPlan = countSelectedTowardPlan(decisions);
  const contentOppHref = withNavContext(
    accountToolHref(selectedClient.slug, "content-opp"),
    clientId,
    from,
    to,
  );
  const decisionEngineHref = accountToolHref(selectedClient.slug, "decision-engine");

  const analysisWindow =
    data?.analysis_from && data?.analysis_to
      ? data.analysis_from === from && data.analysis_to === to
        ? null
        : data.analysis_from === data.analysis_to
          ? data.analysis_from
          : `${data.analysis_from} → ${data.analysis_to}`
      : null;

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs text-[var(--text-tertiary)]">
          Period:{" "}
          <strong className="text-[var(--text-primary)]">{from}</strong> to{" "}
          <strong className="text-[var(--text-primary)]">{to}</strong>
          {analysisWindow ? (
            <>
              {" "}
              · Analyzing <strong className="text-[var(--text-primary)]">{analysisWindow}</strong>
            </>
          ) : null}
        </div>
        {clientId ? <RunEngineButton clientId={clientId} from={from} to={to} /> : null}
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}

      {data && !data.ready ? (
        <Alert variant="info">
          {data.message ?? "Decision Engine is not ready for this client and date range."}
        </Alert>
      ) : null}

      {data ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {Object.entries(data.readiness).map(([key, ready]) => (
            <span key={key} className={`badge ${ready ? "badge-success" : "badge-warning"}`}>
              {readinessLabel(key)}
            </span>
          ))}
        </div>
      ) : null}

      {data?.ready && clientId ? (
        <div className="mt-4 space-y-[var(--section-gap)]">
          <GrowthActionGrid
            levers={data.levers}
            contentOppHref={contentOppHref}
            contentOppCount={searchOpportunities.length}
          />

          <SummaryStrip
            findingsCount={data.findings_count}
            recommendationsCount={recommendations.length}
            selectedCount={selectedTowardPlan}
            growthPlanAllowance={growthPlanAllowance}
            suggestedCount={suggestions.length}
            contentOppHref={contentOppHref}
            contentOppCount={searchOpportunities.length}
          />

          <section className="workspace-section">
            <SectionHeader
              title="Filter by Growth Action"
              description="Narrow recommendations, suggestions, and the findings list without changing scores."
            />
            <GrowthActionFilter
              hrefBase={decisionEngineHref}
              from={from}
              to={to}
              active={leverFilter}
            />
          </section>

          <section id="recommended-actions" className="workspace-section scroll-mt-24">
            <SectionHeader
              title="Recommendations"
              description="Cleared the engine’s impact and confidence thresholds for this period."
              actions={
                <span className="text-xs text-[var(--text-tertiary)]">
                  {filteredRecommendations.length} shown
                </span>
              }
            />

            {filteredRecommendations.length === 0 ? (
              <Alert variant="info">
                No hard recommendations for this filter. Check{" "}
                {filteredSuggestions.length > 0 ? (
                  <>
                    <a href="#suggested-alternatives" className="underline">
                      Suggested alternatives
                    </a>
                    ,{" "}
                  </>
                ) : null}
                <a href="#findings-review" className="underline">
                  All findings
                </a>
                , or{" "}
                <Link href={contentOppHref} className="underline">
                  Content Opp
                </Link>
                .
              </Alert>
            ) : (
              <div className="space-y-3">
                {filteredRecommendations.map((item) => (
                  <RecommendedActionCard
                    key={item.rule_key}
                    item={item}
                    clientId={clientId}
                    from={from}
                    to={to}
                    decision={decisionByRule.get(item.rule_key) ?? null}
                  />
                ))}
              </div>
            )}
          </section>

          {filteredSuggestions.length > 0 ? (
            <section id="suggested-alternatives" className="workspace-section scroll-mt-24">
              <SectionHeader
                title="Suggested alternatives"
                description="Optional extras when recommendations are below your growth-plan allowance. Not threshold promotions."
                actions={
                  <span className="text-xs text-[var(--text-tertiary)]">
                    {filteredSuggestions.length} shown
                  </span>
                }
              />
              <div className="space-y-3">
                {filteredSuggestions.map((item) => (
                  <RecommendedActionCard
                    key={item.rule_key}
                    item={item}
                    clientId={clientId}
                    from={from}
                    to={to}
                    decision={decisionByRule.get(item.rule_key) ?? null}
                  />
                ))}
              </div>
            </section>
          ) : null}

          <FindingsReviewPanel
            findings={filteredFindings}
            recommendedKeys={recommendedKeys}
            suggestedKeys={suggestedKeys}
            clientId={clientId}
            from={from}
            to={to}
            decisionsByRule={decisionByRule}
          />
        </div>
      ) : null}
    </section>
  );
}
