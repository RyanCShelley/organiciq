"use client";

import { useRouter } from "next/navigation";

import { monthName, nextMonth, type RunSummary } from "@/lib/monthly-record";

/**
 * Past runs, newest first. A run is named for the month whose data it read; its
 * plan is for the month after, so the label says both.
 */
export function HistoricalRuns({
  slug,
  runs,
  selected,
}: {
  slug: string;
  runs: RunSummary[];
  selected: string;
}) {
  const router = useRouter();
  return (
    <label className="flex items-center gap-2 text-[13px] text-[var(--text-tertiary)]">
      Historical runs
      <select
        className="min-h-[36px] rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-[13px] text-[var(--text-primary)]"
        value={selected}
        onChange={(event) => router.push(`/${slug}/decision-engine?run=${event.target.value}`)}
      >
        {runs.map((run) => (
          <option key={run.month} value={run.month}>
            {monthName(run.month)} data · plan for {monthName(nextMonth(run.month))}
          </option>
        ))}
      </select>
    </label>
  );
}
