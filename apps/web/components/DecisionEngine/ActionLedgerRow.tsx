"use client";

import { useId, useState } from "react";

import { DecisionActionBar } from "@/components/DecisionEngine/DecisionActionBar";
import {
  demandOf,
  findingActions,
  formatDemand,
  formatEvidence,
  growthActionLabel,
  isPrecondition,
  numberField,
  valueDerivation,
  type Finding,
  type StoredDecision,
} from "@/lib/decision-engine";

/**
 * Whether a row is a site-wide precondition, and why it leads its layer.
 *
 * This used to say what kind of lead figure the row carried — "Flat
 * credit" for the three rules with no clicks-to-leads model, "Measured"
 * for the rest, and "Not valued" for the eight that reached the screen
 * with no figure at all under a green badge claiming they were measured.
 * Nothing carries a lead figure now, so the only distinction left is a
 * real one: a count for one page, or a fix that holds back all of them.
 */
function preconditionChip(finding: Finding) {
  if (!isPrecondition(finding)) return null;
  return {
    label: "Unblocks the rest",
    className: "bg-[#f6ead0] text-[#614a16]",
    title:
      "Site-wide, so it has no count of its own. An engine that cannot fetch the site will not cite any page on it, which is why this comes first.",
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
  const demand = demandOf(finding);
  const minutes = numberField(finding.evidence_json ?? {}, "estimated_minutes");
  const chip = preconditionChip(finding);
  const steps = findingActions(finding.evidence_json ?? {});
  const derivation = valueDerivation(finding);
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
          </span>
        </span>

        {/* The three numbers travel together: below ~640px they wrap under
            the title as one strip rather than each becoming a column one
            word wide, which is what five fixed columns did to a phone. */}
        <span className="ml-10 flex flex-none items-baseline gap-3 sm:ml-0 sm:gap-4">
          <span className="w-auto text-right sm:w-[132px]">
            <span className="font-[family-name:var(--font-display)] text-[21px] font-black leading-none tracking-[-0.02em] text-[var(--text-primary)]">
              {formatDemand(demand)}
            </span>
            {demand ? (
              // The unit sits on the row, not in the heading: 74,000
              // searches and 312 clicks are both in this list and they are
              // not the same thing.
              <span className="ml-1 text-[11px] text-[var(--text-tertiary)]">
                {demand.unit.replace(" / mo", "")}
              </span>
            ) : null}
          </span>

          <span className="w-auto text-right text-[13px] text-[var(--text-secondary)] sm:w-[72px]">
            {minutes === null ? "—" : `${minutes} min`}
          </span>

          <span className="w-auto text-right sm:w-[132px]">
            {chip ? (
              <span
                title={chip.title}
                className={`inline-block whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold ${chip.className}`}
              >
                {chip.label}
              </span>
            ) : null}
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

          {/* One number and where it came from, in place of five 0-100
              bars in a currency nobody could read back as people or as
              minutes — which were the only two questions being asked. */}
          <aside className="border-[var(--border)] lg:border-l lg:pl-7">
            <p className="text-[11.5px] text-[var(--text-tertiary)]">
              {demand ? demand.unit.replace(" / mo", " a month") : "Site-wide"}
            </p>
            <p className="mt-1 font-[family-name:var(--font-display)] text-[44px] font-black leading-none tracking-[-0.035em] text-[var(--text-primary)]">
              {isPrecondition(finding) ? "All" : formatDemand(demand)}
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
            ) : chip ? (
              <p className="mt-5 text-[12.5px] leading-relaxed text-[var(--text-tertiary)]">
                {chip.title}
              </p>
            ) : null}
          </aside>
        </div>
      ) : null}
    </div>
  );
}
