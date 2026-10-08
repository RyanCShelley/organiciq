"use client";

import type { Constraint } from "@/lib/decision-engine";

const LAYER_LABEL: Record<string, string> = {
  visibility: "Visibility",
  traffic: "Traffic",
  conversion: "Leads",
};

const LAYER_BLURB: Record<string, string> = {
  visibility: "The market cannot find you yet",
  traffic: "People can find you and are not clicking",
  conversion: "People arrive and do not become leads",
};

function pct(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined) return "—";
  return `${Math.round(ratio * 100)}%`;
}

/**
 * What this month is about, and why.
 *
 * The engine used to rank ten rules together by expected leads and show the
 * result as a list, which read as a menu. The first thing a strategist needs
 * is not twenty-five options — it is which of the three outcomes is actually
 * holding the client back, with enough of the other two to argue about it.
 */
export function ConstraintBand({
  constraint,
  selected,
  onSelect,
}: {
  constraint: Constraint;
  /** The layer whose actions are lit up below, if any. */
  selected?: string | null;
  onSelect?: (layer: string) => void;
}) {
  const label = LAYER_LABEL[constraint.layer] ?? constraint.layer;
  const counts = constraint.action_counts ?? {};

  return (
    <section
      className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] px-6 py-6"
      aria-label="This month's constraint"
    >
      <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {constraint.by_comparison ? "Weakest this month" : "The constraint this month"}
      </p>

      <h2 className="mt-2 font-[family-name:var(--font-display)] text-[26px] font-black leading-tight tracking-[-0.02em] text-[var(--text-primary)]">
        {label}
      </h2>

      <p className="mt-2 max-w-[80ch] text-[14.5px] leading-relaxed text-[var(--text-secondary)]">
        {/* "This is broken" and "nothing is broken, this is the softest spot"
            are different sentences, and acting on them differs too. */}
        {constraint.by_comparison
          ? `Nothing is below its bar. ${label} has the least room, so it is the softest spot: `
          : `${LAYER_BLURB[constraint.layer] ?? ""} — `}
        {constraint.reason}.
      </p>

      {/* The three readings, so the choice can be argued with rather than
          taken on trust. */}
      <dl className="mt-5 grid gap-3 border-t border-[var(--border)] pt-4 sm:grid-cols-3">
        {constraint.assessments.map((a) => {
          const isChosen = a.layer === constraint.layer;
          const short = a.measurable && a.ratio !== null && a.ratio < a.floor;
          const count = counts[a.layer] ?? 0;
          const isSelected = selected === a.layer;
          // A reading with no actions behind it has nothing to light up,
          // so it stays a tile rather than pretending to be a control.
          const selectable = onSelect !== undefined && count > 0;

          const body = (
            <>
              <dt className="flex items-baseline justify-between gap-2">
                <span className="text-[13px] font-semibold text-[var(--text-primary)]">
                  {LAYER_LABEL[a.layer] ?? a.layer}
                </span>
                <span className="text-[11.5px] text-[var(--text-tertiary)]">
                  {count} {count === 1 ? "action" : "actions"}
                </span>
              </dt>
              <dd className="mt-1 text-left">
                {a.measurable ? (
                  <>
                    <span
                      className={`font-[family-name:var(--font-display)] text-[22px] font-black tabular-nums ${
                        short ? "text-[#8a5e10]" : "text-[var(--text-primary)]"
                      }`}
                    >
                      {pct(a.ratio)}
                    </span>
                    <span className="ml-1.5 text-[11.5px] text-[var(--text-tertiary)]">
                      of {pct(a.floor)} bar
                    </span>
                  </>
                ) : (
                  // Not measurable is not zero. Eighteen clients have no
                  // Search Console; a rung with no inputs must not read as
                  // a catastrophe.
                  <span className="block text-[12.5px] leading-snug text-[var(--text-tertiary)]">
                    {a.reason}
                  </span>
                )}
                {selectable ? (
                  <span className="mt-1.5 block text-[11px] font-semibold text-[var(--brand-teal-deep)]">
                    {isSelected ? "Showing these — click to clear" : "Show these actions"}
                  </span>
                ) : null}
              </dd>
            </>
          );

          const shared = `block w-full rounded-[10px] px-4 py-3 ${
            isSelected
              ? "bg-[var(--surface-muted)] ring-2 ring-[var(--brand-teal-deep)]"
              : isChosen
                ? "bg-[var(--surface-muted)]"
                : ""
          }`;

          return selectable ? (
            <button
              key={a.layer}
              type="button"
              aria-pressed={isSelected}
              onClick={() => onSelect?.(a.layer)}
              className={`${shared} min-h-[44px] cursor-pointer text-left hover:bg-[var(--surface-hover)]`}
            >
              {body}
            </button>
          ) : (
            <div key={a.layer} className={shared}>
              {body}
            </div>
          );
        })}
      </dl>
    </section>
  );
}
