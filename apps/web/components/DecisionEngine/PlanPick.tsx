"use client";

import { useState, useTransition } from "react";

import { setInPlanAction } from "@/app/(app)/[clientSlug]/decision-engine/actions";

/**
 * The lever to disagree with the engine: put a candidate in the month's plan,
 * or take a planned action out of it.
 *
 * The engine recommends; the team decides. Handing the choice back (null) when
 * it agrees with the engine again leaves a re-run free to change its mind.
 */
export function PlanPick({
  uid,
  clientId,
  slug,
  month,
  engineChose,
  inPlan,
}: {
  uid: string;
  clientId: string;
  slug: string;
  month: string;
  /** The engine put it in a slot. */
  engineChose: boolean;
  /** It is in the plan as things stand, after any override. */
  inPlan: boolean;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function choose() {
    setError(null);
    const next = !inPlan;
    startTransition(async () => {
      const result = await setInPlanAction({
        clientId,
        slug,
        month,
        uid,
        inPlan: next === engineChose ? null : next,
      });
      if (!result.ok) setError(result.error);
    });
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={pending}
        onClick={choose}
        className={`min-h-[32px] rounded-lg border px-3 text-[12.5px] font-semibold disabled:opacity-60 ${
          inPlan
            ? "border-[var(--border)] text-[var(--text-secondary)]"
            : "border-[#15784F] bg-[#E5F4EC] text-[#15784F]"
        }`}
      >
        {pending
          ? "Saving…"
          : inPlan
            ? "Take out of the plan"
            : engineChose
              ? "Put back in the plan"
              : "Put in the plan"}
      </button>
      {error ? (
        <span role="alert" className="text-[12.5px] text-[#B4441C]">
          {error}
        </span>
      ) : null}
    </span>
  );
}
