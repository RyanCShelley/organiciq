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

type ScoreFactor = { label: string; value: number };

function scoreFactors(
  item: Pick<Finding, "impact" | "confidence" | "urgency" | "effort" | "severity">,
): ScoreFactor[] {
  return [
    { label: "Impact", value: item.impact },
    ...(item.severity != null ? [{ label: "Severity", value: item.severity }] : []),
    { label: "Confidence", value: item.confidence },
    { label: "Urgency", value: item.urgency },
    { label: "Effort", value: item.effort },
  ];
}

function bandBadgeVariant(band: string | undefined): "danger" | "warning" | "neutral" {
  if (band === "high") return "danger";
  if (band === "medium") return "warning";
  return "neutral";
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
    <article className="highlight-card grid gap-6 p-[var(--card-padding-lg)] lg:grid-cols-[minmax(0,1fr)_216px]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10.5px] font-bold uppercase tracking-[0.1em] text-[var(--brand-teal-deep)]">
            {growthActionLabel(item.lever)}
          </span>
          {band ? (
            <Badge variant={bandBadgeVariant(item.priority_band)}>{band} priority</Badge>
          ) : null}
          <Badge variant="neutral">{stageLabel(item.stage)}</Badge>
          <Badge variant="accent">{item.is_suggested ? "Suggested" : "Recommendation"}</Badge>
          {decision ? (
            <Badge variant={decisionStatusBadgeVariant(decision.status)}>
              {decisionStatusLabel(decision.status)}
            </Badge>
          ) : (
            <Badge variant="neutral">Not evaluated</Badge>
          )}
          <span className="text-xs text-[var(--text-tertiary)]">{item.label}</span>
        </div>

        <h3 className="mt-3 text-pretty font-[family-name:var(--font-display)] text-[17px] font-extrabold leading-snug text-[var(--text-primary)]">
          {item.diagnosis}
        </h3>

        <p className="mt-2 text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
          <span className="font-semibold text-[var(--brand-teal-deep)]">Do this: </span>
          {item.recommended_action}
        </p>

        <p className="mt-3 font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]">
          {formatEvidence(item.evidence_json)}
        </p>

        {explanations.length > 0 ? (
          <ul className="mt-2 list-disc space-y-0.5 pl-4 text-[13px] text-[var(--text-secondary)]">
            {explanations.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}

        {item.priority_band_reason ? (
          <p className="mt-2 text-xs text-[var(--text-secondary)]">
            Band reason:{" "}
            <span className="font-medium text-[var(--text-primary)]">
              {item.priority_band_reason}
            </span>
          </p>
        ) : null}

        {canAct && clientId && from && to ? (
          <DecisionActionBar
            clientId={clientId}
            from={from}
            to={to}
            ruleKey={item.rule_key}
            decision={decision}
          />
        ) : null}
      </div>

      <div className="flex flex-col gap-3 border-[var(--border)] lg:border-l lg:pl-[22px]">
        <div>
          <div className="text-[11px] text-[var(--text-tertiary)]">Priority score</div>
          <div className="font-[family-name:var(--font-display)] text-[28px] font-black leading-none tracking-[-0.02em] text-[var(--text-primary)]">
            {item.priority_score.toFixed(1)}
          </div>
        </div>

        {scoreFactors(item).map((factor) => (
          <div key={factor.label}>
            <div className="flex justify-between text-[11.5px] text-[var(--text-secondary)]">
              <span>{factor.label}</span>
              <span className="font-semibold tabular-nums">{factor.value}</span>
            </div>
            <div className="progress-track mt-1 h-[5px] overflow-hidden rounded-full">
              <div
                className="progress-fill h-full rounded-full"
                style={{ width: scoreBar(Number(factor.value)) }}
              />
            </div>
          </div>
        ))}

        <div className="mt-auto pt-1 text-[11.5px] text-[var(--text-tertiary)]">
          Success metric
          <span className="mt-0.5 block font-semibold text-[var(--text-primary)]">
            {item.success_metric}
          </span>
        </div>
      </div>
    </article>
  );
}
