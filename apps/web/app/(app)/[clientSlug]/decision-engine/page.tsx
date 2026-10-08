import Link from "next/link";

import { ActionLedger } from "@/components/DecisionEngine/ActionLedger";
import { ConstraintBand } from "@/components/DecisionEngine/ConstraintBand";
import { EngineStatusBand } from "@/components/DecisionEngine/EngineStatusBand";
import { RunEngineButton } from "@/components/DecisionEngine/RunEngineButton";
import { Alert } from "@/components/ui/Alert";
import { apiFetch, type Client } from "@/lib/api";
import { accountToolHref } from "@/lib/account-routes";
import { requireAccountClient } from "@/lib/account-routes.server";
import { resolveDateRange } from "@/lib/context";
import {
  countSelectedTowardPlan,
  normalizeDiagnoseResponse,
  SOURCE_LABELS,
  type DiagnoseResponse,
  type StoredDecision,
} from "@/lib/decision-engine";
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
    const [diagnose, stored, client] = await Promise.all([
      apiFetch<DiagnoseResponse>(
        `/decisions/diagnose?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        { clientId },
      ),
      apiFetch<StoredDecision[]>(
        `/decisions?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        { clientId },
      ).catch(() => [] as StoredDecision[]),
      apiFetch<Client>(`/clients/${clientId}`, { clientId }),
    ]);
    data = normalizeDiagnoseResponse(diagnose);
    decisions = stored;
    // The server resolves this. Deriving it here meant fetching
    // `/admin/tiers`, which a client-role user is forbidden to call — so
    // the whole page failed for exactly the people it is written for.
    growthPlanAllowance = client.growth_action_allowance ?? 0;
    if (client.plan_label) planLabel = client.plan_label;
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load Decision Engine";
  }

  const searchOpportunities = data?.search_opportunities ?? [];

  // The engine decides what a growth action is and what order they come
  // in; this reads its answer.
  //
  // Never truncated to the allowance: the plan says how many are included
  // this month, not how many are worth seeing. The ledger draws the line.
  const actions = data?.growth_actions ?? [];
  const blocking = data?.blocking_findings ?? [];
  const constraint = data?.constraint ?? null;

  const decisionByRule = new Map(decisions.map((row) => [row.rule_key, row]));
  const selectedTowardPlan = countSelectedTowardPlan(decisions);
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
          {constraint ? <ConstraintBand constraint={constraint} /> : null}

          <p className="max-w-[76ch] text-[14.5px] leading-relaxed text-[var(--text-secondary)]">
            {constraint
              ? "The constraint's work comes first. Everything else is still here, ranked by how many people it is about."
              : "Everything the engine found that could be done in an hour, ranked by how many people it is about."}{" "}
            The line falls where the plan does — the ranking is advice, not a rule.
            {selectedTowardPlan > 0
              ? ` ${selectedTowardPlan} accepted so far this period.`
              : ""}
          </p>

          <ActionLedger
            actions={actions}
            blocking={blocking}
            allowance={growthPlanAllowance}
            planLabel={planLabel}
            clientId={clientId}
            from={from}
            to={to}
            decisionsByRule={decisionByRule}
          />

          {/* One way out of this page, to the list that is not actions.
              What stood here was a count of "findings not competing for a
              slot" beside a panel that re-ranked those same findings on
              the old 0-100 scale — so the screen ranked by leads at the
              top and by a different, unexplained number at the bottom. */}
          <Link
            href={contentOppHref}
            className="inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-5 text-[13.5px] font-semibold no-underline"
          >
            See content opportunities
            {searchOpportunities.length > 0 ? (
              <span className="text-[var(--text-tertiary)]">
                ({searchOpportunities.length})
              </span>
            ) : null}
          </Link>

          <EngineStatusBand
            data={data}
            findingsCount={data.findings_count}
            from={from}
            to={to}
          />
        </div>
      ) : null}
    </section>
  );
}
