import { cn } from "@/lib/cn";

/**
 * Share of tracked prompts where the brand shows up, and how prominently.
 *
 * Computed from the rows already on the page — same reasoning as the position
 * distribution: the summary and the table beneath it cannot disagree.
 */
export type AiPresenceRow = {
  brand_mentioned: boolean | null;
  brand_cited: boolean | null;
  mention_position: number | null;
  url_position: number | null;
};

const TOP_N = 3;

type Measure = {
  key: string;
  label: string;
  hint: string;
  count: (rows: AiPresenceRow[]) => number;
  barClassName: string;
};

export const AI_PRESENCE_MEASURES: Measure[] = [
  {
    key: "mention",
    label: "Answers with a mention",
    hint: "Brand named anywhere in the answer",
    count: (rows) => rows.filter((row) => row.brand_mentioned === true).length,
    barClassName: "bg-[var(--brand-teal)]",
  },
  {
    key: "link",
    label: "Answers with a link",
    hint: "Brand cited as a source",
    count: (rows) => rows.filter((row) => row.brand_cited === true).length,
    barClassName: "bg-[var(--brand-lime)]",
  },
  {
    key: "mention_top3",
    label: `Mention in top ${TOP_N}`,
    hint: "Named among the first few brands",
    count: (rows) =>
      rows.filter((row) => row.mention_position !== null && row.mention_position <= TOP_N).length,
    barClassName: "bg-[var(--brand-teal-deep)]",
  },
  {
    key: "link_top3",
    label: `Link in top ${TOP_N}`,
    hint: "Cited among the first few sources",
    count: (rows) =>
      rows.filter((row) => row.url_position !== null && row.url_position <= TOP_N).length,
    barClassName: "bg-[#4d6b0a]",
  },
];

export function AiPresenceSummary({
  rows,
  className,
}: {
  rows: AiPresenceRow[];
  className?: string;
}) {
  const total = rows.length;
  if (total === 0) return null;

  return (
    <div className={cn("card p-[var(--card-padding)]", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
          Mention and link presence
        </h3>
        <span className="text-xs text-[var(--text-tertiary)]">
          across {total.toLocaleString()} tracked prompt{total === 1 ? "" : "s"}
        </span>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {AI_PRESENCE_MEASURES.map((measure) => {
          const count = measure.count(rows);
          const pct = (count / total) * 100;
          return (
            <div key={measure.key}>
              <div className="flex items-baseline justify-between gap-2">
                <span
                  className="text-[12.5px] font-semibold text-[var(--text-secondary)]"
                  title={measure.hint}
                >
                  {measure.label}
                </span>
                <span className="text-[12.5px] tabular-nums text-[var(--text-primary)]">
                  <span className="font-bold">{pct.toFixed(1)}%</span>
                  <span className="ml-1.5 text-[var(--text-tertiary)]">
                    {count}/{total}
                  </span>
                </span>
              </div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-[#F1F2F3]">
                <div
                  className={cn("h-full rounded-full", measure.barClassName)}
                  style={{ width: `${Math.min(100, pct)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
