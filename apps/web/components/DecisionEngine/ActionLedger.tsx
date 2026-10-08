import { ActionLedgerRow } from "@/components/DecisionEngine/ActionLedgerRow";
import {
  expectedLeadsMonthly,
  numberField,
  type Finding,
  type StoredDecision,
} from "@/lib/decision-engine";

function planWord(count: number): string {
  return count === 1 ? "1 action" : `${count} actions`;
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
  belowFloor,
  unvalued = [],
  blocking = [],
  allowance,
  planLabel,
  clientId,
  from,
  to,
  decisionsByRule,
}: {
  actions: Finding[];
  belowFloor: Finding[];
  /** Actions the engine could not price. A bug, shown rather than hidden. */
  unvalued?: Finding[];
  /** What has to be fixed before anything below it can be trusted. */
  blocking?: Finding[];
  allowance: number;
  planLabel: string;
  clientId?: string;
  from?: string;
  to?: string;
  decisionsByRule: Map<string, StoredDecision>;
}) {
  const included = allowance > 0 ? actions.slice(0, allowance) : actions;
  const beyond = allowance > 0 ? actions.slice(allowance) : [];
  const short = allowance > 0 && actions.length < allowance;

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
            Ranked by expected leads a month
          </h2>
          <p className="text-xs text-[var(--text-tertiary)]">
            {actions.length.toLocaleString()} {actions.length === 1 ? "action" : "actions"} worth an
            hour or less
          </p>
        </div>

        <div
          aria-hidden="true"
          className="hidden gap-4 px-6 pb-2 text-[11px] uppercase tracking-[0.04em] text-[var(--text-tertiary)] sm:flex"
        >
          <span className="w-6 flex-none">#</span>
          <span className="min-w-0 flex-1">What and where</span>
          <span className="w-[104px] flex-none text-right">Leads / mo</span>
          <span className="w-[72px] flex-none text-right">Time</span>
          <span className="w-[112px] flex-none text-right">Basis</span>
        </div>

        {included.map((item, index) => (
          <ActionLedgerRow
            key={item.rule_key}
            finding={item}
            rank={index + 1}
            beyondPlan={false}
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

        {beyond.length > 0 ? (
          <>
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-t-2 border-b-[var(--border)] border-t-[var(--text-primary)] bg-[var(--surface-muted)] px-6 py-3.5">
              <span className="text-xs font-bold uppercase tracking-[0.06em] text-[var(--text-primary)]">
                {planLabel} ends here · {planWord(allowance)}
              </span>
              <span className="text-[13px] text-[var(--text-secondary)]">
                Below is real work that did not fit this month.
              </span>
            </div>
            {beyond.map((item, index) => (
              <ActionLedgerRow
                key={item.rule_key}
                finding={item}
                rank={allowance + index + 1}
                beyondPlan
                clientId={clientId}
                from={from}
                to={to}
                decision={decisionsByRule.get(item.rule_key) ?? null}
              />
            ))}
          </>
        ) : null}
      </div>

      {unvalued.length > 0 ? (
        <div className="mt-4 rounded-[var(--radius-lg,14px)] border border-[var(--danger-border,#e0bcbc)] bg-[var(--danger-soft,#fdf3f3)] px-6 py-4">
          <p className="text-[14px] font-semibold text-[var(--text-primary)]">
            {unvalued.length} {unvalued.length === 1 ? "action" : "actions"} could not be valued
          </p>
          <p className="mt-1.5 max-w-[80ch] text-[13px] leading-relaxed text-[var(--text-secondary)]">
            They are held back rather than ranked against work that has a number. This is a bug in
            the engine, not a judgement about the work.
          </p>
          <ul className="mt-3 space-y-1.5">
            {unvalued.map((item) => (
              <li key={item.rule_key} className="text-[13px] text-[var(--text-secondary)]">
                {item.diagnosis}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {belowFloor.length > 0 ? (
        <details className="mt-4 rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] px-6 py-4">
          <summary className="flex min-h-[44px] cursor-pointer items-center text-[13.5px] font-semibold text-[var(--brand-teal-deep)]">
            Considered and not offered ({belowFloor.length})
          </summary>
          <p className="mt-2 max-w-[80ch] text-[13px] leading-relaxed text-[var(--text-tertiary)]">
            Below a tenth of a lead a month. Shown so the floor can be argued with rather than taken
            on trust — if these look worth an hour to you, the floor is wrong, not the work.
          </p>
          <ul className="mt-4 space-y-3">
            {belowFloor.map((item) => (
              <li
                key={item.rule_key}
                className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-t border-[var(--border)] pt-3 text-[13.5px]"
              >
                <span className="min-w-[54px] font-[family-name:var(--font-display)] font-extrabold tabular-nums text-[var(--text-tertiary)]">
                  {(expectedLeadsMonthly(item) ?? 0).toFixed(3)}
                </span>
                <span className="min-w-0 flex-1 text-[var(--text-secondary)]">
                  {item.diagnosis}
                </span>
                <span className="text-xs text-[var(--text-tertiary)]">
                  {describeShortfall(item)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

/**
 * The inputs behind a number that came out too small.
 *
 * A page with nothing left to recover and an estimate that lost its
 * inputs both print 0.000; only these say which it is.
 */
function describeShortfall(item: Finding): string {
  const evidence = item.evidence_json ?? {};
  const sessions = numberField(evidence, "sessions");
  const leads = numberField(evidence, "leads");
  const benchmark = numberField(evidence, "benchmark_rate_pct");
  const shortfall = numberField(evidence, "shortfall_leads");
  if (sessions === null) return "";
  return [
    `${sessions.toLocaleString()} sessions`,
    `${leads ?? 0} leads`,
    benchmark === null ? null : `benchmark ${benchmark.toFixed(2)}%`,
    shortfall === null ? null : `shortfall ${shortfall}`,
  ]
    .filter(Boolean)
    .join(", ");
}
