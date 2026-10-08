"use client";

import { useState } from "react";

import { ActionLedger } from "@/components/DecisionEngine/ActionLedger";
import { ConstraintBand } from "@/components/DecisionEngine/ConstraintBand";
import type { Constraint, Finding, StoredDecision } from "@/lib/decision-engine";

/**
 * The constraint and the work, holding one piece of state between them.
 *
 * The band answers "which outcome is holding this client back" and the
 * ledger answers "what would you do about it", and until now a reader had
 * to join those up by eye — the band says Leads has one action, and
 * finding that action means reading twenty-six rows looking for the one
 * that is about leads.
 *
 * Clicking a reading picks its work out of the list. It dims rather than
 * filters: the order is the engine's argument about what matters, and
 * hiding two thirds of it to answer "which of these are about leads"
 * would throw the argument away to answer the question.
 */
export function DecisionBoard({
  constraint,
  actions,
  blocking,
  allowance,
  planLabel,
  clientId,
  from,
  to,
  decisionsByRule,
  selectedTowardPlan,
}: {
  constraint: Constraint | null;
  actions: Finding[];
  blocking: Finding[];
  allowance: number;
  planLabel: string;
  clientId?: string;
  from?: string;
  to?: string;
  decisionsByRule: Map<string, StoredDecision>;
  selectedTowardPlan: number;
}) {
  const [highlight, setHighlight] = useState<string | null>(null);

  return (
    <div className="space-y-[var(--section-gap)]">
      {constraint ? (
        <ConstraintBand
          constraint={constraint}
          selected={highlight}
          onSelect={(layer) =>
            setHighlight((current) => (current === layer ? null : layer))
          }
        />
      ) : null}

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
        allowance={allowance}
        planLabel={planLabel}
        clientId={clientId}
        from={from}
        to={to}
        decisionsByRule={decisionsByRule}
        highlight={highlight}
        onClearHighlight={() => setHighlight(null)}
      />
    </div>
  );
}
