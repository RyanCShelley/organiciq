import Link from "next/link";

import { FindingsReviewPanel } from "@/components/DecisionEngine/FindingsReviewPanel";
import { GrowthActionFilter } from "@/components/DecisionEngine/GrowthActionFilter";
import { GrowthActionGrid } from "@/components/DecisionEngine/GrowthActionGrid";
import { RecommendedActionCard } from "@/components/DecisionEngine/RecommendedActionCard";
import { RunEngineButton } from "@/components/DecisionEngine/RunEngineButton";
import { SummaryStrip } from "@/components/DecisionEngine/SummaryStrip";
import { Alert } from "@/components/ui/Alert";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch, type Client, type Tier } from "@/lib/api";
import { resolveClientId, resolveDateRange } from "@/lib/context";
import {
  applyPlanMinimum,
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
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const clientId = await resolveClientId(params);
  const { from, to } = await resolveDateRange(params);
  const leverFilter =
    typeof params.lever === "string" && params.lever.length > 0 ? params.lever : "all";

  let data: DiagnoseResponse | null = null;
  let decisions: StoredDecision[] = [];
  let planMin = 0;
  let error: string | null = null;

  if (!clientId) {
    error = "Select a client to run the Decision Engine.";
  } else {
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
      planMin = resolvePlanAllowances(client, tier).growthActionAllowance;
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load Decision Engine";
    }
  }

  const allFindings: Finding[] = data?.findings ?? [];
  const additionalFindings = allFindings.filter((finding) => !finding.is_recommended_action);
  const searchOpportunities = data?.search_opportunities ?? [];
  const promoted = data?.recommended_actions ?? [];
  const withPlanFloor = applyPlanMinimum(promoted, additionalFindings, planMin);
  const recommendedKeys = new Set(promoted.map((item) => item.rule_key));
  const planFillKeys = new Set(
    withPlanFloor.filter((item) => item.plan_fill).map((item) => item.rule_key),
  );
  const filteredActions =
    leverFilter === "all"
      ? withPlanFloor
      : withPlanFloor.filter((item) => item.lever === leverFilter);
  const filteredFindings =
    leverFilter === "all" ? allFindings : allFindings.filter((item) => item.lever === leverFilter);
  const decisionByRule = new Map(decisions.map((row) => [row.rule_key, row]));
  const contentOppHref = clientId
    ? withNavContext("/content-opp", clientId, from, to)
    : "/content-opp";

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
      <PageHeader
        title="Decision Engine"
        description="Engine shortlist plus full findings for human review. Content opportunities live under Content Opp."
        meta={
          <>
            <span>
              Period: <strong className="text-[var(--text-primary)]">{from}</strong> to{" "}
              <strong className="text-[var(--text-primary)]">{to}</strong>
            </span>
            {analysisWindow ? (
              <>
                <span className="text-[var(--text-tertiary)]">·</span>
                <span>
                  Analyzing{" "}
                  <strong className="text-[var(--text-primary)]">{analysisWindow}</strong>
                </span>
              </>
            ) : null}
            {planMin > 0 ? (
              <>
                <span className="text-[var(--text-tertiary)]">·</span>
                <span>Plan floor: {planMin} Growth Actions</span>
              </>
            ) : null}
          </>
        }
        actions={
          clientId ? <RunEngineButton clientId={clientId} from={from} to={to} /> : null
        }
      />

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
          <GrowthActionGrid levers={data.levers} />

          <SummaryStrip
            findingsCount={data.findings_count}
            recommendedCount={withPlanFloor.length}
            planMin={planMin}
            reviewCount={filteredFindings.length}
            contentOppHref={contentOppHref}
            contentOppCount={searchOpportunities.length}
          />

          <section className="workspace-section">
            <SectionHeader
              title="Filter by Growth Action"
              description="Narrow the shortlist and review table without changing scores."
            />
            <GrowthActionFilter clientId={clientId} from={from} to={to} active={leverFilter} />
          </section>

          <section id="recommended-actions" className="workspace-section scroll-mt-24">
            <SectionHeader
              title="Engine shortlist"
              description="What the engine promoted for this period. You still decide — review the full findings list below to override."
              actions={
                <span className="text-xs text-[var(--text-tertiary)]">
                  {filteredActions.length} shown
                  {planMin > 0 ? ` · plan ${planMin}` : ""}
                </span>
              }
            />

            {filteredActions.length === 0 ? (
              <Alert variant="info">
                No promoted actions for this filter. Check{" "}
                <a href="#findings-review" className="underline">
                  All findings
                </a>{" "}
                or{" "}
                <Link href={contentOppHref} className="underline">
                  Content Opp
                </Link>
                .
              </Alert>
            ) : (
              <div className="space-y-3">
                {filteredActions.map((item) => (
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

          <FindingsReviewPanel
            findings={filteredFindings}
            recommendedKeys={recommendedKeys}
            planFillKeys={planFillKeys}
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
