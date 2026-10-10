"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { runMonthlyRecordAction } from "@/app/(app)/[clientSlug]/decision-engine/actions";
import { monthName } from "@/lib/monthly-record";

/** The last `count` months, newest first, as `YYYY-MM`. */
function recentMonths(from: string, count = 13): string[] {
  const [year, month] = from.split("-").map(Number);
  const out: string[] = [];
  for (let i = 0; i < count; i += 1) {
    const d = new Date(Date.UTC(year, month - 1 - i, 1));
    out.push(
      `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`,
    );
  }
  return out;
}

/**
 * Run a month, from the page that shows it.
 *
 * The month is a choice rather than "now", because a month is reviewed once
 * it has finished: the usual press is November asking for October. A finished
 * month is judged as of its last day, so its month-to-date measures cover the
 * whole month and not the few days elapsed in the month somebody is sitting
 * in. The button names the month it will replace before it replaces it.
 */
export function RunEngineButton({
  clientId,
  slug,
  month,
  currentMonth,
}: {
  clientId: string;
  slug: string;
  /** The run on screen, which is what the picker opens on. */
  month: string;
  /** The month we are actually in, which bounds the list. */
  currentMonth: string;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [chosen, setChosen] = useState(month);
  const router = useRouter();

  const months = recentMonths(currentMonth);

  function run() {
    setError(null);
    startTransition(async () => {
      const result = await runMonthlyRecordAction(clientId, slug, chosen);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      // Land on what was just written rather than whatever ?run= pointed at.
      router.replace(`/${slug}/decision-engine?run=${result.month}`);
      router.refresh();
    });
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-2">
        <label className="sr-only" htmlFor="run-month">
          Month to run
        </label>
        <select
          id="run-month"
          className="min-h-[36px] rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-[13px] text-[var(--text-primary)]"
          value={chosen}
          disabled={pending}
          onChange={(e) => setChosen(e.target.value)}
        >
          {months.map((m) => (
            <option key={m} value={m}>
              {monthName(m)}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={run}
          disabled={pending}
          className="inline-flex min-h-[36px] items-center rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3.5 text-[13px] font-semibold text-[var(--text-primary)] disabled:opacity-60"
        >
          {pending ? "Running…" : "Run"}
        </button>
      </div>
      <p className="text-[11.5px] text-[var(--text-tertiary)]">
        {chosen === currentMonth
          ? "Runs to today, and replaces this month's saved record"
          : `Runs all of ${monthName(chosen)}, and replaces its saved record`}
      </p>
      {error ? (
        <p role="alert" className="max-w-[40ch] text-right text-[12px] text-[#B4441C]">
          {error}
        </p>
      ) : null}
    </div>
  );
}
