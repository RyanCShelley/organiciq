"use client";

import { ActionLedgerRow } from "@/components/DecisionEngine/ActionLedgerRow";
import { type Finding, type StoredDecision } from "@/lib/decision-engine";

const LAYER_LABEL: Record<string, string> = {
  visibility: "Visibility",
  traffic: "Traffic",
  conversion: "Leads",
};

function planWord(count: number): string {
  return count === 1 ? "1 action" : `${count} actions`;
}

/**
 * Visibility and traffic are mass nouns and read the same at any count.
 * "Leads" does not — "1 leads" is the kind of seam that makes a number
 * look generated rather than counted.
 */
function layerWord(layer: string, count: number): string {
  if (layer === "conversion") return count === 1 ? "lead" : "leads";
  return layer;
}

/**
 * Every action the engine found, ranked, with the plan's line drawn across it.
 *
 * The line is stated rather than implied by truncating the list. The
 * allowance says how many are included this month, not how many are worth
 * knowing about — a Launch client with three good actions should see all
 * three and choose which one to spend on.
 */
export function ActionLedger({
  actions,
  blocking = [],
  allowance,
  planLabel,
  clientId,
  from,
  to,
  decisionsByRule,
  highlight = null,
  onClearHighlight,
}: {
  actions: Finding[];
  /** What has to be fixed before anything below it can be trusted. */
  blocking?: Finding[];
  allowance: number;
  planLabel: string;
  clientId?: string;
  from?: string;
  to?: string;
  decisionsByRule: Map<string, StoredDecision>;
  /** Lit up by the constraint band: the layer whose work to pick out. */
  highlight?: string | null;
  onClearHighlight?: () => void;
}) {
  const included = allowance > 0 ? actions.slice(0, allowance) : actions;
  const beyond = allowance > 0 ? actions.slice(allowance) : [];
  const litBelowTheLine = beyond.filter((item) => item.stage === highlight).length;
  const litTotal = actions.filter((item) => item.stage === highlight).length;
  const short = allowance > 0 && actions.length < allowance;
  // What is down there, by outcome, so the closed summary still says
  // something: "18 visibility, 3 leads" is a reason to open it or not.
  const beyondSummary = Object.entries(
    beyond.reduce<Record<string, number>>((acc, item) => {
      const layer = item.stage ?? "other";
      acc[layer] = (acc[layer] ?? 0) + 1;
      return acc;
    }, {}),
  )
    .sort((a, b) => b[1] - a[1])
    .map(([layer, n]) => `${n} ${layerWord(layer, n)}`)
    .join(", ");

  return (
    <section id="growth-actions" className="scroll-mt-24">
      {/* A plan can be empty because there is nothing to do, or because a
          gate upstream says the numbers it would be built from are wrong.
          Those are opposite situations and must not look the same. */}
      {blocking.length > 0 ? (
        <div className="mb-4 rounded-[var(--radius-lg,14px)] border border-[var(--danger-border,#e0bcbc)] bg-[var(--danger-soft,#fdf3f3)] px-6 py-5">
          <p className="font-[family-name:var(--font-display)] text-[16px] font-extrabold text-[var(--text-primary)]">
            Fix this first
          </p>
          <p className="mt-1.5 max-w-[86ch] text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
            {actions.length === 0
              ? "No actions are offered this month. Everything below depends on numbers this says cannot be trusted."
              : "Some work is held back: it depends on numbers this says cannot be trusted."}
          </p>
          <ul className="mt-3 space-y-2">
            {blocking.map((item) => (
              <li
                key={item.rule_key}
                className="text-[14px] font-semibold leading-snug text-[var(--text-primary)]"
              >
                {item.diagnosis}
                {item.recommended_action ? (
                  <span className="mt-1 block text-[13px] font-normal text-[var(--text-secondary)]">
                    {item.recommended_action}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="overflow-hidden rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)]">
        <div className="flex flex-wrap items-baseline justify-between gap-3 px-6 pb-3 pt-5">
          <h2 className="font-[family-name:var(--font-display)] text-[17px] font-extrabold text-[var(--text-primary)]">
            The constraint first, then by how many people
          </h2>
          <p className="text-xs text-[var(--text-tertiary)]">
            {actions.length.toLocaleString()} {actions.length === 1 ? "action" : "actions"} worth an
            hour or less
          </p>
        </div>

        {/* Nothing is removed from the list when a layer is picked out: the
            order is the engine's argument, and hiding two thirds of it to
            answer "which of these are about leads" would throw the argument
            away to answer the question. */}
        {highlight ? (
          <div className="flex flex-wrap items-baseline justify-between gap-3 border-t border-[var(--border)] bg-[var(--surface-muted)] px-6 py-2.5">
            <p className="text-[12.5px] text-[var(--text-secondary)]">
              {litTotal} {litTotal === 1 ? "action" : "actions"} for{" "}
              <span className="font-semibold text-[var(--text-primary)]">
                {LAYER_LABEL[highlight] ?? highlight}
              </span>
              , in place. The rest are dimmed, not hidden.
            </p>
            {onClearHighlight ? (
              <button
                type="button"
                onClick={onClearHighlight}
                className="min-h-[32px] cursor-pointer text-[12.5px] font-semibold text-[var(--brand-teal-deep)] underline-offset-2 hover:underline"
              >
                Show all
              </button>
            ) : null}
          </div>
        ) : null}

        <div
          aria-hidden="true"
          className="hidden gap-4 px-6 pb-2 text-[11px] uppercase tracking-[0.04em] text-[var(--text-tertiary)] sm:flex"
        >
          <span className="w-6 flex-none">#</span>
          <span className="min-w-0 flex-1">What and where</span>
          <span className="w-[132px] flex-none text-right">People / mo</span>
          <span className="w-[72px] flex-none text-right">Time</span>
          <span className="w-[132px] flex-none text-right" />
        </div>

        {included.map((item, index) => (
          <ActionLedgerRow
            key={item.rule_key}
            finding={item}
            rank={index + 1}
            beyondPlan={false}
            dimmed={highlight !== null && item.stage !== highlight}
            clientId={clientId}
            from={from}
            to={to}
            decision={decisionsByRule.get(item.rule_key) ?? null}
          />
        ))}

        {actions.length === 0 ? (
          <p className="border-t border-[var(--border)] px-6 py-8 text-[14px] text-[var(--text-secondary)]">
            {blocking.length > 0
              ? "Nothing is offered while the above is unresolved."
              : "Nothing cleared the floor this period."}
          </p>
        ) : null}

        {/* The empty slots, shown as deliberate. The old screen filled
            them from the findings list and called it "Suggested
            alternatives", which is padding with a label on it. */}
        {short ? (
          <div className="border-t-2 border-[var(--text-primary)] bg-[var(--surface-muted)] px-6 py-4">
            <p className="text-[14px] font-semibold text-[var(--text-primary)]">
              {actions.length} of {allowance} slots filled
            </p>
            <p className="mt-1 max-w-[80ch] text-[13px] leading-relaxed text-[var(--text-secondary)]">
              {blocking.length > 0 ? (
                <>
                  Held back by what is above, not by a shortage of work. Resolve it and re-run.
                </>
              ) : (
                <>
                  There is no{" "}
                  {allowance - actions.length === 1 ? "other action" : "further action"} worth an
                  hour this month. The{" "}
                  {allowance - actions.length === 1 ? "slot stays" : "slots stay"} empty rather
                  than being filled with weaker work.
                </>
              )}
            </p>
          </div>
        ) : null}

        {/* Everything past the plan line, collapsed. Twenty-six open rows is
            the menu this screen is trying to stop being; the work is still
            here, and still in order, behind one click. */}
        {beyond.length > 0 ? (
          <details className="group" open={litBelowTheLine > 0}>
            <summary className="flex min-h-[44px] cursor-pointer flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-t-2 border-b-[var(--border)] border-t-[var(--text-primary)] bg-[var(--surface-muted)] px-6 py-3.5">
              <span className="text-xs font-bold uppercase tracking-[0.06em] text-[var(--text-primary)]">
                {planLabel} ends here · {planWord(allowance)}
              </span>
              <span className="text-[13px] text-[var(--text-secondary)]">
                {beyond.length} more {beyond.length === 1 ? "action" : "actions"} did not fit
                this month{beyondSummary ? ` — ${beyondSummary}` : ""}
              </span>
            </summary>
            {beyond.map((item, index) => (
              <ActionLedgerRow
                key={item.rule_key}
                finding={item}
                rank={allowance + index + 1}
                beyondPlan
                dimmed={highlight !== null && item.stage !== highlight}
                clientId={clientId}
                from={from}
                to={to}
                decision={decisionsByRule.get(item.rule_key) ?? null}
              />
            ))}
          </details>
        ) : null}
      </div>

    </section>
  );
}
