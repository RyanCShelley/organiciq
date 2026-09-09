import { DecisionActionBar } from "@/components/DecisionEngine/DecisionActionBar";
import { Badge } from "@/components/ui/Badge";
import {
  decisionStatusBadgeVariant,
  decisionStatusLabel,
  formatEvidence,
  formatPriorityBand,
  growthActionLabel,
  impactExplanation,
  scoreBar,
  stageLabel,
  type Finding,
  type StoredDecision,
} from "@/lib/decision-engine";

function ScoreGrid({
  item,
}: {
  item: Pick<Finding, "impact" | "confidence" | "urgency" | "effort" | "severity">;
}) {
  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
      {[
        ["Impact", item.impact],
        ...(item.severity != null ? [["Severity", item.severity] as const] : []),
        ["Confidence", item.confidence],
        ["Urgency", item.urgency],
        ["Effort", item.effort],
      ].map(([label, value]) => (
        <div key={String(label)}>
          <div className="mb-1 flex justify-between text-[0.6875rem] text-[var(--text-tertiary)]">
            <span>{label}</span>
            <span className="tabular-nums text-[var(--text-secondary)]">{value}</span>
          </div>
          <div className="progress-track h-1.5 rounded-full">
            <div
              className="progress-fill h-1.5 rounded-full"
              style={{ width: scoreBar(Number(value)) }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function RecommendedActionCard({
  item,
  clientId,
  from,
  to,
  decision,
}: {
  item: Finding;
  clientId?: string;
  from?: string;
  to?: string;
  decision?: StoredDecision | null;
}) {
  const explanations = impactExplanation(item.evidence_json);
  const band = formatPriorityBand(item.priority_band);
  const canAct = Boolean(clientId && from && to);

  return (
    <article className="highlight-card p-[var(--card-padding-lg)]">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="accent">{item.plan_fill ? "Suggested growth action" : "Recommended"}</Badge>
        <Badge variant="neutral">{growthActionLabel(item.lever)}</Badge>
        <Badge variant="neutral">{stageLabel(item.stage)}</Badge>
        {decision ? (
          <Badge variant={decisionStatusBadgeVariant(decision.status)}>
            {decisionStatusLabel(decision.status)}
          </Badge>
        ) : (
          <Badge variant="neutral">Not evaluated</Badge>
        )}
        <span className="text-xs text-[var(--text-tertiary)]">{item.label}</span>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
        <div>
          <span className="text-[var(--text-tertiary)]">Priority Score </span>
          <span className="font-semibold text-[var(--text-primary)]">
            {item.priority_score.toFixed(1)}
          </span>
        </div>
        {band ? (
          <div>
            <span className="text-[var(--text-tertiary)]">Priority Band </span>
            <span className="font-semibold text-action-emphasis">{band}</span>
          </div>
        ) : null}
      </div>

      <h3 className="mt-2 text-base font-bold leading-snug">{item.diagnosis}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-secondary)]">
        {formatEvidence(item.evidence_json)}
      </p>

      {explanations.length > 0 ? (
        <ul className="mt-2 list-disc space-y-0.5 pl-4 text-sm text-[var(--text-secondary)]">
          {explanations.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}

      <div className="mt-3 grid gap-2 lg:grid-cols-2">
        <div className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-muted)] p-3 text-sm">
          <p className="text-[0.625rem] font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]">
            Recommended Action
          </p>
          <p className="mt-1 text-[var(--text-primary)]">{item.recommended_action}</p>
        </div>
        <div className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-muted)] p-3 text-sm">
          <p className="text-[0.625rem] font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]">
            Success Metric
          </p>
          <p className="mt-1 text-[var(--text-secondary)]">{item.success_metric}</p>
        </div>
      </div>

      {item.priority_band_reason ? (
        <p className="mt-2 text-xs text-[var(--text-secondary)]">
          Band reason:{" "}
          <span className="font-medium text-[var(--text-primary)]">{item.priority_band_reason}</span>
        </p>
      ) : null}

      <ScoreGrid item={item} />

      {canAct && clientId && from && to ? (
        <DecisionActionBar
          clientId={clientId}
          from={from}
          to={to}
          ruleKey={item.rule_key}
          decision={decision}
        />
      ) : null}
    </article>
  );
}
