"use client";

import { Fragment, useState } from "react";

import { DecisionActionBar } from "@/components/DecisionEngine/DecisionActionBar";
import { Badge } from "@/components/ui/Badge";
import { SectionHeader } from "@/components/ui/SectionHeader";
import {
  decisionStatusBadgeVariant,
  decisionStatusLabel,
  findingSubject,
  formatEvidence,
  impactExplanation,
  promotionBlockedLabel,
  scoreBar,
  stageLabel,
  type Finding,
  type StoredDecision,
} from "@/lib/decision-engine";

function ExpandedFinding({
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
  const canAct = Boolean(clientId && from && to);

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
            Recommended Action
          </p>
          <p className="mt-1 text-[var(--text-primary)]">{item.recommended_action}</p>
        </div>
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
  );
}

export function AdditionalFindingsPanel({
  findings,
  clientId,
  from,
  to,
  decisionsByRule,
}: {
  findings: Finding[];
  clientId?: string;
  from?: string;
  to?: string;
  decisionsByRule?: Map<string, StoredDecision>;
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  if (findings.length === 0) return null;

  return (
    <section id="additional-findings" className="workspace-section scroll-mt-24">
      <SectionHeader
        title="Additional Findings"
        description="Diagnostic observations not promoted to recommended actions. Accept or dismiss any of them."
        actions={<span className="text-xs text-[var(--text-tertiary)]">{findings.length} for review</span>}
      />

      <div className="table-shell overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Growth Action</th>
              <th>Subject</th>
              <th>Stage</th>
              <th className="text-right">Finding Score</th>
              <th>Not Promoted</th>
              <th>Status</th>
              <th aria-label="Expand" />
            </tr>
          </thead>
          <tbody>
            {findings.map((item) => {
              const isOpen = expandedKey === item.rule_key;
              const decision = decisionsByRule?.get(item.rule_key) ?? null;
              return (
                <Fragment key={item.rule_key}>
                  <tr className="align-top">
                    <td className="whitespace-nowrap">{item.label}</td>
                    <td className="max-w-xs">
                      <span className="line-clamp-2 break-all">{findingSubject(item)}</span>
                    </td>
                    <td className="whitespace-nowrap text-[var(--text-secondary)]">
                      {stageLabel(item.stage)}
                    </td>
                    <td className="whitespace-nowrap text-right font-medium tabular-nums">
                      {item.priority_score.toFixed(1)}
                    </td>
                    <td className="max-w-sm text-[var(--text-secondary)]">
                      {promotionBlockedLabel(item.promotion_blocked_reason)}
                    </td>
                    <td className="whitespace-nowrap">
                      {decision ? (
                        <Badge variant={decisionStatusBadgeVariant(decision.status)}>
                          {decisionStatusLabel(decision.status)}
                        </Badge>
                      ) : (
                        <span className="text-xs text-[var(--text-tertiary)]">—</span>
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
                      <td colSpan={7} className="p-0">
                        <ExpandedFinding
                          item={item}
                          clientId={clientId}
                          from={from}
                          to={to}
                          decision={decision}
                        />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
