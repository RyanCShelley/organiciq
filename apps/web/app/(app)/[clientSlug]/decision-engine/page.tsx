import Link from "next/link";

import { ActionLedger } from "@/components/DecisionEngine/ActionLedger";
import { EngineStatusBand } from "@/components/DecisionEngine/EngineStatusBand";
import { FindingsReviewPanel } from "@/components/DecisionEngine/FindingsReviewPanel";
import { RunEngineButton } from "@/components/DecisionEngine/RunEngineButton";
import { Alert } from "@/components/ui/Alert";
import { apiFetch, type Client, type Tier } from "@/lib/api";
import { accountToolHref } from "@/lib/account-routes";
import { requireAccountClient } from "@/lib/account-routes.server";
import { resolveDateRange } from "@/lib/context";
import {
  countSelectedTowardPlan,
  isBelowFloor,
  normalizeDiagnoseResponse,
  rankActions,
  SOURCE_LABELS,
  type DiagnoseResponse,
  type Finding,
  type StoredDecision,
} from "@/lib/decision-engine";
import { resolvePlanAllowances } from "@/lib/plan-allowances";
import { withNavContext } from "@/lib/navigation";

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

  let data: DiagnoseResponse | null = null;
  let decisions: StoredDecision[] = [];
  let growthPlanAllowance = 0;
  let planLabel = "This plan";
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
    if (tier?.tier_name) planLabel = `${tier.tier_name} plan`;
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load Decision Engine";
  }

  const allFindings: Finding[] = data?.findings ?? [];
  const searchOpportunities = data?.search_opportunities ?? [];

  // Ranked by expected leads a month, and never truncated to the
  // allowance: the plan says how many are included this month, not how
  // many are worth seeing. The line is drawn inside the ledger instead.
  const ranked = rankActions(data?.recommended_actions ?? []);
  const actions = ranked.filter((item) => !isBelowFloor(item));
  const belowFloor = ranked.filter(isBelowFloor);

  const recommendedKeys = new Set(actions.map((item) => item.rule_key));
  const decisionByRule = new Map(decisions.map((row) => [row.rule_key, row]));
  const selectedTowardPlan = countSelectedTowardPlan(decisions);
  const coreWork = allFindings.filter((item) => !recommendedKeys.has(item.rule_key));
  const contentOppHref = withNavContext(
    accountToolHref(selectedClient.slug, "content-opp"),
    clientId,
    from,
    to,
  );

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            Growth actions
          </p>
          <h1 className="mt-1.5 font-[family-name:var(--font-display)] text-[30px] font-black leading-tight tracking-[-0.02em] text-[var(--text-primary)]">
            {selectedClient.client_name ?? selectedClient.slug}
          </h1>
          <p className="mt-1.5 text-[13.5px] text-[var(--text-secondary)]">
            {planLabel}
            {growthPlanAllowance > 0
              ? ` · ${growthPlanAllowance} included this month`
              : ""}{" "}
            · {from} to {to}
          </p>
        </div>
        {clientId ? <RunEngineButton clientId={clientId} from={from} to={to} /> : null}
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}

      {data && !data.ready ? (
        <Alert variant="danger">
          {data.message ?? "Decision Engine is not ready for this client and date range."}
          <span className="mt-2 block text-xs">
            Missing:{" "}
            {Object.entries(data.readiness)
              .filter(([, ready]) => !ready)
              .map(([key]) => SOURCE_LABELS[key] ?? key)
              .join(", ")}
          </span>
        </Alert>
      ) : null}

      {data?.ready && clientId ? (
        <div className="space-y-[var(--section-gap)]">
          <EngineStatusBand
            data={data}
            findingsCount={data.findings_count}
            from={from}
            to={to}
          />

          <p className="max-w-[76ch] text-[14.5px] leading-relaxed text-[var(--text-secondary)]">
            Everything the engine found that could be done in an hour, ranked by what it is worth.
            The line falls where the plan does — the ranking is advice, not a rule.
            {selectedTowardPlan > 0
              ? ` ${selectedTowardPlan} accepted so far this period.`
              : ""}
          </p>

          <ActionLedger
            actions={actions}
            belowFloor={belowFloor}
            allowance={growthPlanAllowance}
            planLabel={planLabel}
            clientId={clientId}
            from={from}
            to={to}
            decisionsByRule={decisionByRule}
          />

          <section className="workspace-section">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="font-[family-name:var(--font-display)] text-[16px] font-extrabold text-[var(--text-primary)]">
                  Not competing for a slot
                </h2>
                <p className="mt-1.5 max-w-[70ch] text-[13.5px] text-[var(--text-secondary)]">
                  {coreWork.length.toLocaleString()} findings are core work the plan already covers,
                  or opportunities that need a decision before they can become a task.
                </p>
              </div>
              <Link
                href={contentOppHref}
                className="inline-flex min-h-[44px] items-center rounded-lg border border-[var(--border)] px-4 text-[13.5px] font-semibold no-underline"
              >
                Content Opp ({searchOpportunities.length})
              </Link>
            </div>
          </section>

          <FindingsReviewPanel
            findings={allFindings}
            recommendedKeys={recommendedKeys}
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
