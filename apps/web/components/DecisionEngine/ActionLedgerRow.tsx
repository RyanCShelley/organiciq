"use client";

import { useId, useState } from "react";

import { DecisionActionBar } from "@/components/DecisionEngine/DecisionActionBar";
import {
  expectedLeadsMonthly,
  findingActions,
  formatEvidence,
  growthActionLabel,
  numberField,
  stringField,
  valueDerivation,
  type Finding,
  type StoredDecision,
} from "@/lib/decision-engine";

/**
 * What kind of number this is — or that there isn't one.
 *
 * The third branch is the one that matters: this defaulted to "Measured"
 * for anything that was not a flat credit, including rows that carried no
 * valuation at all. Eight of those reached the screen, each showing an em
 * dash for leads and for time under a green badge claiming it was
 * measured. An unvalued row is a bug, and it has to look like one.
 */
function basisChip(finding: Finding) {
  const basis = stringField(finding.evidence_json ?? {}, "value_basis");
  if (basis === "flat_credit") {
    return {
      label: "Flat credit",
      className: "bg-[#f6ead0] text-[#614a16]",
      title:
        "A placeholder credit. There is no honest clicks-to-leads model for this action yet, so every one of its kind carries the same value and the search volume breaks the tie.",
    };
  }
  if (basis === null || expectedLeadsMonthly(finding) === null) {
    return {
      label: "Not valued",
      className: "bg-[#f3e2e2] text-[#6b2b2b]",
      title:
        "The engine could not put a lead estimate on this. It should not be competing for an action; please report it.",
    };
  }
  return {
    label: "Measured",
    className: "bg-[#d9f3e4] text-[#2c4a3e]",
    title:
      "The sessions and the leads were counted. What is estimated is that the fix recovers them.",
  };
}

function subject(finding: Finding): string {
  if (finding.page_url) return finding.page_url.replace(/^https?:\/\/[^/]+/, "") || "/";
  return finding.query ?? "site-wide";
}

/**
 * One line of the ledger, which opens into the whole action.
 *
 * The collapsed row carries only what a choice is made on — what, where,
 * what it is worth, what it costs. Everything else waits until someone
 * asks for it, because twenty-six rows of full cards is the screen this
 * replaces.
 */
export function ActionLedgerRow({
  finding,
  rank,
  beyondPlan,
  clientId,
  from,
  to,
  decision,
}: {
  finding: Finding;
  rank: number;
  beyondPlan: boolean;
  clientId?: string;
  from?: string;
  to?: string;
  decision?: StoredDecision | null;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const leads = expectedLeadsMonthly(finding);
  const minutes = numberField(finding.evidence_json ?? {}, "estimated_minutes");
  const chip = basisChip(finding);
  const steps = findingActions(finding.evidence_json ?? {});
  const derivation = valueDerivation(finding);
  const tiebreak = numberField(finding.evidence_json ?? {}, "tiebreak_volume");
  const evidence = formatEvidence(finding.evidence_json ?? {});

  return (
    <div
      className={`border-t border-[var(--border)] ${beyondPlan ? "bg-[var(--surface-muted)]" : ""}`}
    >
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full min-h-[44px] cursor-pointer flex-wrap items-start gap-x-4 gap-y-3 px-6 py-5 text-left hover:bg-[var(--surface-hover)]"
      >
        <span className="w-6 flex-none pt-0.5 font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-tertiary)]">
          {rank}
        </span>

        <span className="min-w-0 flex-[999_1_240px]">
          <span className="block text-[14.5px] font-semibold leading-snug text-[var(--text-primary)]">
            {finding.diagnosis}
          </span>
          <span className="mt-1 block break-words font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]">
            {subject(finding)}
            {tiebreak ? ` · nearest tracked term: ${tiebreak.toLocaleString()} searches / mo` : ""}
          </span>
        </span>

        {/* The three numbers travel together: below ~640px they wrap under
            the title as one strip rather than each becoming a column one
            word wide, which is what five fixed columns did to a phone. */}
        <span className="ml-10 flex flex-none items-baseline gap-3 sm:ml-0 sm:gap-4">
          <span className="w-auto text-right font-[family-name:var(--font-display)] sm:w-[104px] text-[21px] font-black leading-none tracking-[-0.02em] text-[var(--text-primary)]">
            {leads === null ? "—" : leads.toFixed(2)}
          </span>

          <span className="w-auto text-right text-[13px] text-[var(--text-secondary)] sm:w-[72px]">
            {minutes === null ? "—" : `${minutes} min`}
          </span>

          <span className="w-auto text-right sm:w-[112px]">
            <span
              title={chip.title}
              className={`inline-block whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold ${chip.className}`}
            >
              {chip.label}
            </span>
          </span>
        </span>
      </button>

      {open ? (
        <div id={panelId} className="grid gap-8 px-6 pb-7 pt-1 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0">
            <p className="text-[10.5px] font-bold uppercase tracking-[0.1em] text-[var(--brand-teal-deep)]">
              {growthActionLabel(finding.lever)}
            </p>

            <div className="mt-4">
              <p className="text-[11px] font-bold uppercase tracking-[0.08em] text-[var(--text-tertiary)]">
                Do this{minutes === null ? "" : ` · ${minutes} minutes`}
              </p>
              {steps.length > 0 ? (
                <ol className="mt-3 list-decimal space-y-3 pl-5">
                  {steps.map((step) => (
                    <li key={step.text} className="text-[14.5px] leading-relaxed">
                      {step.text}
                      {step.detail ? (
                        <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--text-tertiary)]">
                          {step.detail}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="mt-3 text-[14.5px] leading-relaxed">{finding.recommended_action}</p>
              )}
            </div>

            {evidence ? (
              <p className="mt-5 border-t border-[var(--border)] pt-4 font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]">
                {evidence}
              </p>
            ) : null}

            <p className="mt-3 text-xs text-[var(--text-tertiary)]">
              Verify with{" "}
              <span className="font-semibold text-[var(--text-primary)]">
                {finding.success_metric}
              </span>
            </p>

            {clientId && from && to ? (
              <DecisionActionBar
                clientId={clientId}
                from={from}
                to={to}
                ruleKey={finding.rule_key}
                decision={decision}
              />
            ) : null}
          </div>

          {/* One number and the arithmetic behind it, in place of five
              0-100 bars in a currency nobody could read back as leads or
              as minutes — which were the only two questions being asked. */}
          <aside className="border-[var(--border)] lg:border-l lg:pl-7">
            <p className="text-[11.5px] text-[var(--text-tertiary)]">Expected leads / month</p>
            <p className="mt-1 font-[family-name:var(--font-display)] text-[44px] font-black leading-none tracking-[-0.035em] text-[var(--text-primary)]">
              {leads === null ? "—" : leads.toFixed(2)}
            </p>

            {derivation.length > 0 ? (
              <dl className="mt-5 rounded-[10px] bg-[var(--surface-muted)] p-4">
                <p className="text-[11px] font-bold uppercase tracking-[0.08em] text-[var(--text-tertiary)]">
                  How we got there
                </p>
                <div className="mt-3 space-y-2.5">
                  {derivation.map((row) => (
                    <div key={row.label} className="flex justify-between gap-3 text-[13px]">
                      <dt className="text-[var(--text-secondary)]">{row.label}</dt>
                      <dd className="font-[family-name:var(--font-display)] font-extrabold tabular-nums text-[var(--text-primary)]">
                        {row.value}
                      </dd>
                    </div>
                  ))}
                </div>
              </dl>
            ) : (
              <p className="mt-5 text-[12.5px] leading-relaxed text-[var(--text-tertiary)]">
                {chip.title}
              </p>
            )}
          </aside>
        </div>
      ) : null}
    </div>
  );
}
