import type { MonthlyRecord } from "@/lib/monthly-record";

type Row = MonthlyRecord["previous_results"][number];

const RESULT_CHIP: Record<string, string> = {
  improved: "bg-[#E5F4EC] text-[#15784F]",
  no_change: "bg-[#EEF1F3] text-[#3E4954]",
  worse: "bg-[#FBE9E2] text-[#8E3414]",
  waiting: "bg-[#EEF1F3] text-[#3E4954]",
};

const RESULT_LABEL: Record<string, string> = {
  improved: "Improved",
  no_change: "No change",
  worse: "Worse",
  waiting: "Not checked yet",
};

/** Two decimals only where the metric needs them. */
function fmt(value: number | null | undefined): string {
  if (value == null) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

/** What became of last month's work, each on the metric it was meant to move. */
export function PreviousResults({ rows, empty }: { rows: Row[]; empty: string }) {
  if (rows.length === 0) {
    return <p className="mt-3 text-[13px] text-[var(--text-tertiary)]">{empty}</p>;
  }
  return (
    <ul className="mt-3 space-y-2.5 text-[13px]">
      {rows.map((row, index) => (
        <li key={`${row.action_uid}-${index}`}>
          <div className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 flex-1">{row.title}</span>
            <span className="shrink-0 tabular-nums text-[var(--text-secondary)]">
              {fmt(row.before)} → {fmt(row.after)}
            </span>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                RESULT_CHIP[row.result ?? "waiting"]
              }`}
            >
              {RESULT_LABEL[row.result ?? "waiting"]}
            </span>
            <span className="text-[11.5px] text-[var(--text-tertiary)]">{row.metric}</span>
            {/* A verdict on work nobody recorded doing is about the metric,
                not about the work. */}
            {row.result !== "waiting" && !row.shipped ? (
              <span className="text-[11.5px] text-[#8A4B08]">not recorded as shipped</span>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
