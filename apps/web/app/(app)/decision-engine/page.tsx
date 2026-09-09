import { revalidatePath } from "next/cache";
import Link from "next/link";

import { AdditionalFindingsPanel } from "@/components/DecisionEngine/AdditionalFindingsPanel";
import { GrowthActionFilter } from "@/components/DecisionEngine/GrowthActionFilter";
import { GrowthActionGrid } from "@/components/DecisionEngine/GrowthActionGrid";
import { RecommendedActionCard } from "@/components/DecisionEngine/RecommendedActionCard";
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
  type StoredDecision,
} from "@/lib/decision-engine";
import { resolvePlanAllowances } from "@/lib/plan-allowances";
import { withNavContext } from "@/lib/navigation";

function readinessLabel(key: string): string {
  if (key === "search_console") return "Search Console";
  if (key === "crawl_audit") return "Crawl / Audit";
  return key;
}

async function evaluateDecisions(formData: FormData) {
  "use server";

  const clientId = String(formData.get("clientId") || "");
  const from = String(formData.get("from") || "");
  const to = String(formData.get("to") || "");
  if (!clientId || !from || !to) return;

  await apiFetch("/decisions/evaluate", {
    method: "POST",
    clientId,
    body: { from, to },
  });
  revalidatePath("/decision-engine");
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

  const additionalFindings =
    data?.findings.filter((finding) => !finding.is_recommended_action) ?? [];
  const searchOpportunities = data?.search_opportunities ?? [];
  const promoted = data?.recommended_actions ?? [];
  const withPlanFloor = applyPlanMinimum(promoted, additionalFindings, planMin);
  const filteredActions =
    leverFilter === "all"
      ? withPlanFloor
      : withPlanFloor.filter((item) => item.lever === leverFilter);
  const filteredAdditional =
    leverFilter === "all"
      ? additionalFindings.filter(
          (finding) => !withPlanFloor.some((item) => item.rule_key === finding.rule_key),
        )
      : additionalFindings.filter(
          (finding) =>
            finding.lever === leverFilter &&
            !withPlanFloor.some((item) => item.rule_key === finding.rule_key),
        );
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
        description="Recommended Growth Actions for this period. Content opportunities live under Content Opp."
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
          clientId ? (
            <form action={evaluateDecisions}>
              <input type="hidden" name="clientId" value={clientId} />
              <input type="hidden" name="from" value={from} />
              <input type="hidden" name="to" value={to} />
              <button type="submit" className="btn btn-primary btn-sm">
                Evaluate period
              </button>
            </form>
          ) : null
        }
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}

      {data?.partial_message ? <Alert variant="info">{data.partial_message}</Alert> : null}

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
          <SummaryStrip
            findingsCount={data.findings_count}
            recommendedCount={withPlanFloor.length}
            planMin={planMin}
            additionalCount={filteredAdditional.length}
            contentOppHref={contentOppHref}
            contentOppCount={searchOpportunities.length}
          />

          <section className="workspace-section">
            <SectionHeader
              title="Filter by Growth Action"
              description="Narrow recommended actions and findings without changing scores."
            />
            <GrowthActionFilter clientId={clientId} from={from} to={to} active={leverFilter} />
          </section>

          <section id="recommended-actions" className="workspace-section scroll-mt-24">
            <SectionHeader
              title="Recommended Actions"
              description="Promoted findings plus plan-floor fills from the next-best scored findings when needed."
              actions={
                <span className="text-xs text-[var(--text-tertiary)]">
                  {filteredActions.length} shown
                  {planMin > 0 ? ` · plan ${planMin}` : ""}
                </span>
              }
            />

            {filteredActions.length === 0 ? (
              <Alert variant="info">
                No findings for this Growth Action filter.{" "}
                <Link href={contentOppHref} className="underline">
                  Review Content Opp
                </Link>{" "}
                for striking-distance pages.
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

          <GrowthActionGrid levers={data.levers} />
          <AdditionalFindingsPanel
            findings={filteredAdditional}
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
