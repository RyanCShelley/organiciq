"use client";

import { useMemo, useState, useTransition } from "react";

import { setInPlanAction } from "@/app/(app)/[clientSlug]/decision-engine/actions";
import { BRANCH_LABEL, type Candidate, type SlotState } from "@/lib/monthly-record";

const BRANCH_CHIP: Record<string, string> = {
  visibility: "bg-[#E9EEF8] text-[#2C4A86]",
  traffic: "bg-[#EEF1F3] text-[#3E4954]",
  leads: "bg-[#FBE9E2] text-[#8E3414]",
};

function path(url: string): string {
  return url.replace(/^https?:\/\/[^/]+/, "") || "/";
}

/**
 * Everything the engine weighed, and the lever to disagree with it.
 *
 * SMA's October had 67 viable actions: five in slots, four named as skipped,
 * and 58 that existed nowhere a reader could see them. The engine ranks on
 * what it can measure; it does not know the team is on a larger project this
 * month, or that the capabilities pages are being rebuilt. So the ranking is
 * a starting position, shown in full, and anything here can be put into the
 * plan or taken out of it.
 */
export function OptionsPanel({
  candidates,
  states,
  clientId,
  slug,
  month,
}: {
  candidates: Candidate[];
  states: Map<string, SlotState>;
  clientId: string;
  slug: string;
  month: string;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [branch, setBranch] = useState<string>("all");
  const [showAll, setShowAll] = useState(false);

  const rows = useMemo(
    () => candidates.filter((c) => branch === "all" || c.branch === branch),
    [candidates, branch],
  );
  const visible = showAll ? rows : rows.slice(0, 15);
  const branches = [...new Set(candidates.map((c) => c.branch))];

  /** In the plan: what the engine said, unless somebody said otherwise. */
  function inPlan(row: Candidate): boolean {
    const override = states.get(row.action_uid)?.in_plan;
    return override ?? row.slot !== null;
  }

  function toggle(row: Candidate) {
    setError(null);
    const next = !inPlan(row);
    // Back to null when the choice agrees with the engine again, so a
    // re-run with better data is free to change its mind.
    const value = next === (row.slot !== null) ? null : next;
    startTransition(async () => {
      const result = await setInPlanAction({
        clientId,
        slug,
        month,
        uid: row.action_uid,
        inPlan: value,
      });
      if (!result.ok) setError(result.error);
    });
  }

  if (candidates.length === 0) return null;

  return (
    <section
      aria-labelledby="options-heading"
      className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] px-6 py-5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2
          id="options-heading"
          className="font-[family-name:var(--font-display)] text-[18px] font-extrabold text-[var(--text-primary)]"
        >
          Everything the engine weighed
        </h2>
        <p className="text-[13px] text-[var(--text-secondary)]">
          {candidates.length} action{candidates.length === 1 ? "" : "s"} ranked.
          Put any of them in the plan.
        </p>
      </div>
      <p className="mt-1 max-w-[80ch] text-[13px] leading-relaxed text-[var(--text-secondary)]">
        The ranking is what the engine can measure. It does not know what the
        team is already committed to, so it is a starting position rather than
        an answer.
      </p>

      {error ? (
        <p role="alert" className="mt-2 text-[12.5px] text-[#B4441C]">
          {error}
        </p>
      ) : null}

      {branches.length > 1 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {["all", ...branches].map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setBranch(key)}
              className={`min-h-[30px] rounded-full border px-3 text-[12.5px] font-semibold ${
                branch === key
                  ? "border-[var(--brand-teal-deep)] text-[var(--text-primary)]"
                  : "border-[var(--border)] text-[var(--text-secondary)]"
              }`}
            >
              {key === "all" ? "All" : BRANCH_LABEL[key] ?? key}
            </button>
          ))}
        </div>
      ) : null}

      <ul className="mt-3">
        {visible.map((row) => {
          const chosen = inPlan(row);
          const overridden = (states.get(row.action_uid)?.in_plan ?? null) !== null;
          return (
            <li
              key={row.action_uid}
              className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-[var(--border)] py-2.5"
            >
              <button
                type="button"
                disabled={pending}
                onClick={() => toggle(row)}
                className={`min-h-[30px] shrink-0 rounded-lg border px-3 text-[12.5px] font-semibold disabled:opacity-60 ${
                  chosen
                    ? "border-[#15784F] bg-[#E5F4EC] text-[#15784F]"
                    : "border-[var(--border)] text-[var(--text-secondary)]"
                }`}
              >
                {chosen ? "In the plan" : "Add"}
              </button>

              <span className="font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]">
                {row.id}
              </span>
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                  BRANCH_CHIP[row.branch] ?? BRANCH_CHIP.traffic
                }`}
              >
                {BRANCH_LABEL[row.branch] ?? row.branch}
              </span>

              <span className="min-w-[240px] flex-1 text-[13.5px] text-[var(--text-primary)]">
                {row.title}
                <span className="ml-2 font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]">
                  {path(row.target_url)}
                </span>
              </span>

              <span className="shrink-0 text-[12px] text-[var(--text-tertiary)]">
                {row.effort_min} min
                {overridden ? " · your call" : ""}
                {/* Why the engine left it out — the thing you are overruling. */}
                {!chosen && row.not_slotted_because ? (
                  <span className="ml-2">{row.not_slotted_because}</span>
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>

      {rows.length > visible.length ? (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="mt-3 text-[13px] font-semibold text-[var(--brand-teal-hover)] underline"
        >
          Show the other {rows.length - visible.length}
        </button>
      ) : null}
    </section>
  );
}
