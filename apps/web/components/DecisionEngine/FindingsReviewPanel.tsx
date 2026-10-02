"use client";

import { Fragment, useState } from "react";

import { DecisionActionBar } from "@/components/DecisionEngine/DecisionActionBar";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { SectionHeader } from "@/components/ui/SectionHeader";
import {
  decisionStatusBadgeVariant,
  decisionStatusLabel,
  findingSubject,
  formatEvidence,
  impactExplanation,
  findingState,
  promotionBlockedLabel,
  scoreBar,
  type Finding,
  type StoredDecision,
} from "@/lib/decision-engine";

/**
 * The cascade, as the engine orders it.
 *
 * Visibility earns traffic and traffic earns leads, so a finding about leads
 * outranks one about rankings however they score. Grouping by that makes the
 * order legible — a flat list sorted by score hides the fact that the engine
 * thinks in layers, and hides a blocking gate entirely.
 */
const STAGE_ORDER = ["conversion", "traffic", "visibility"] as const;

const STAGE_HEADINGS: Record<string, { title: string; blurb: string }> = {
  conversion: { title: "Leads", blurb: "Traffic arriving and not converting." },
  traffic: { title: "Traffic", blurb: "Rankings not turning into visits." },
  visibility: { title: "Visibility", blurb: "Not being found in the first place." },
};

function groupByStage(findings: Finding[]): [string, Finding[]][] {
  const groups = new Map<string, Finding[]>();
  for (const item of findings) {
    const key = STAGE_ORDER.includes(item.stage as (typeof STAGE_ORDER)[number])
      ? item.stage
      : "visibility";
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return STAGE_ORDER.filter((stage) => groups.has(stage)).map((stage) => [
    stage,
    groups.get(stage) ?? [],
  ]);
}

/**
 * Effort as a size, not a number. Two findings worth the same are not the
 * same job, and the queue orders the top of the list by what each costs —
 * so the cost has to be visible, or the order looks arbitrary.
 */
const EFFORT_LABELS: Record<string, { label: string; title: string }> = {
  S: { label: "S", title: "Small — an edit to one page" },
  M: { label: "M", title: "Medium — a page's worth of work" },
  L: { label: "L", title: "Large — a new page, or a rewrite" },
};

function EffortChip({ item }: { item: Finding }) {
  const size = String(item.evidence_json?.effort_class ?? "");
  const meta = EFFORT_LABELS[size];
  if (!meta) return null;
  return (
    <span
      title={meta.title}
      className="ml-2 inline-flex h-4 w-4 items-center justify-center rounded-[3px] bg-[var(--surface-muted)] text-[10px] font-bold text-[var(--text-tertiary)]"
    >
      {meta.label}
    </span>
  );
}

function engineStatus(item: Finding, recommendedKeys: Set<string>, suggestedKeys: Set<string>): {
  label: string;
  variant: "success" | "warning" | "neutral" | "accent" | "danger";
  hint?: string;
} {
  switch (findingState(item, recommendedKeys, suggestedKeys)) {
    case "blocked":
      return {
        label: "Blocked",
        variant: "danger",
        hint: "Scored from data a failed check says cannot be trusted. Clear that first.",
      };
    case "retired":
      return {
        label: "Rule contested",
        variant: "warning",
        hint: `Dismissed ${item.override_count} times on different pages — rewrite or retire this rule.`,
      };
    case "recommended":
      return { label: "Recommendation", variant: "success" };
    case "core-work":
      return {
        label: "Core work",
        variant: "neutral",
        hint: "Monthly upkeep, already in the plan — it does not spend a growth action.",
      };
    case "suggested":
      return { label: "Suggested", variant: "accent" };
    default:
      return {
        label: promotionBlockedLabel(item.promotion_blocked_reason),
        variant: "warning",
      };
  }
}

function ExpandedFinding({
  item,
  clientId,
  from,
  to,
  decision,
  statusLabel,
}: {
  item: Finding;
  clientId?: string;
  from?: string;
  to?: string;
  decision?: StoredDecision | null;
  statusLabel: string;
}) {
  const explanations = impactExplanation(item.evidence_json);
  const canAct = Boolean(clientId && from && to);
  const isEnginePick = statusLabel === "Recommendation" || statusLabel === "Suggested";

  return (
    <div className="border-t border-[var(--border)] bg-[var(--surface-muted)] px-3 py-3 text-sm">
      <p className="font-medium text-[var(--text-primary)]">{item.diagnosis}</p>
      <p className="mt-1.5 text-[var(--text-secondary)]">{formatEvidence(item.evidence_json)}</p>
      {explanations.length > 0 ? (
        <ul className="mt-2 list-disc space-y-0.5 pl-4 text-[var(--text-secondary)]">
          {explanations.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
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
              <span className="tabular-nums">{value}</span>
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

      {item.recommended_action ? (
        <div className="mt-3 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-3">
          <p className="text-[0.625rem] font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]">
            Suggested action
          </p>
          <p className="mt-1 text-[var(--text-primary)]">{item.recommended_action}</p>
        </div>
      ) : null}

      {canAct && clientId && from && to ? (
        <>
          {!isEnginePick ? (
            <p className="mt-3 text-xs text-[var(--text-secondary)]">
              Engine did not promote this — Accept to override and take it anyway.
            </p>
          ) : null}
          <DecisionActionBar
            clientId={clientId}
            from={from}
            to={to}
            ruleKey={item.rule_key}
            decision={decision}
          />
        </>
      ) : null}
    </div>
  );
}

/** Full finding list for human review — engine promotion is a signal, not the only option. */
export function FindingsReviewPanel({
  findings,
  recommendedKeys,
  suggestedKeys,
  clientId,
  from,
  to,
  decisionsByRule,
}: {
  findings: Finding[];
  recommendedKeys: Set<string>;
  suggestedKeys: Set<string>;
  clientId?: string;
  from?: string;
  to?: string;
  decisionsByRule?: Map<string, StoredDecision>;
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const needsReview = findings.filter(
    (item) => !recommendedKeys.has(item.rule_key) && !suggestedKeys.has(item.rule_key),
  ).length;

  return (
    <section id="findings-review" className="workspace-section scroll-mt-24">
      <SectionHeader
        title="All findings — your review"
        description="Everything the engine detected for this period. Recommendations and suggestions above are shortcuts; use Accept / Dismiss here to override."
        actions={
          <span className="text-xs text-[var(--text-tertiary)]">
            {findings.length} total
            {needsReview > 0 ? ` · ${needsReview} not promoted` : ""}
          </span>
        }
      />

      {findings.length === 0 ? (
        <Alert variant="info">
          No diagnostic findings for this Growth Action filter in the analysis window.
        </Alert>
      ) : (
        <div className="table-shell overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Growth Action</th>
                <th>Subject</th>
                <th className="text-right">Score</th>
                <th>Engine status</th>
                <th>Your status</th>
                <th aria-label="Expand" />
              </tr>
            </thead>
            {groupByStage(findings).map(([stage, rows]) => (
            <tbody key={stage}>
              <tr>
                <th
                  colSpan={6}
                  className="bg-[var(--surface-muted)] text-left text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]"
                >
                  {STAGE_HEADINGS[stage]?.title ?? stage}
                  <span className="ml-2 font-normal normal-case tracking-normal text-[var(--text-tertiary)]">
                    {STAGE_HEADINGS[stage]?.blurb} · {rows.length}
                  </span>
                </th>
              </tr>
              {rows.map((item) => {
                const isOpen = expandedKey === item.rule_key;
                const decision = decisionsByRule?.get(item.rule_key) ?? null;
                const status = engineStatus(item, recommendedKeys, suggestedKeys);
                return (
                  <Fragment key={item.rule_key}>
                    <tr className="align-top">
                      <td className="whitespace-nowrap">
                        {item.label}
                        <EffortChip item={item} />
                      </td>
                      <td className="max-w-xs">
                        <span className="line-clamp-2 break-all">{findingSubject(item)}</span>
                      </td>
                      <td className="whitespace-nowrap text-right font-medium tabular-nums">
                        {item.priority_score.toFixed(1)}
                      </td>
                      <td className="max-w-sm">
                        <Badge variant={status.variant}>{status.label}</Badge>
                        {/* A one-word badge cannot say why a row is not an
                            action. "Core work" and "Blocked" mean very
                            different things to whoever picks this up. */}
                        {status.hint ? (
                          <div className="mt-1 text-[11.5px] leading-snug text-[var(--text-tertiary)]">
                            {status.hint}
                          </div>
                        ) : null}
                      </td>
                      <td className="whitespace-nowrap">
                        {decision ? (
                          <Badge variant={decisionStatusBadgeVariant(decision.status)}>
                            {decisionStatusLabel(decision.status)}
                          </Badge>
                        ) : (
                          <span className="text-xs text-[var(--text-tertiary)]">Open</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap">
                        <button
                          type="button"
                          onClick={() => setExpandedKey(isOpen ? null : item.rule_key)}
                          className="btn btn-ghost btn-sm"
                          aria-expanded={isOpen}
                        >
                          {isOpen ? "Hide" : "Details"}
                        </button>
                      </td>
                    </tr>
                    {isOpen ? (
                      <tr>
                        <td colSpan={6} className="p-0">
                          <ExpandedFinding
                            item={item}
                            clientId={clientId}
                            from={from}
                            to={to}
                            decision={decision}
                            statusLabel={status.label}
                          />
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
            ))}
          </table>
        </div>
      )}
    </section>
  );
}
