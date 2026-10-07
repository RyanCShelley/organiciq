import { SOURCE_LABELS, type DiagnoseResponse } from "@/lib/decision-engine";

function formatDay(iso: string | null | undefined): string {
  if (!iso) return "not synced";
  const parsed = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

function daysBetween(a: string, b: string): number | null {
  const from = Date.parse(`${a}T00:00:00Z`);
  const to = Date.parse(`${b}T00:00:00Z`);
  if (Number.isNaN(from) || Number.isNaN(to)) return null;
  return Math.round((to - from) / 86_400_000);
}

/**
 * What the run was actually built from, stated plainly at the foot of the page.
 *
 * Nothing here is behind a disclosure. The whole point of the section is
 * to explain a date range that is not the one someone picked, and an
 * explanation you have to click for does not explain anything — the
 * question it answers is asked while looking at the dates, not after
 * deciding to go hunting.
 */
export function EngineStatusBand({
  data,
  findingsCount,
  from,
  to,
}: {
  data: DiagnoseResponse;
  findingsCount: number;
  from: string;
  to: string;
}) {
  const analysedTo = data.analysis_to ?? to;
  const analysedFrom = data.analysis_from ?? from;
  // The engine stops where the data stops. When that is short of the date
  // someone chose, say so here rather than letting the header and the
  // dates silently disagree.
  const shortBy = daysBetween(analysedTo, to);
  const narrowed = shortBy !== null && shortBy > 0;

  return (
    <section
      className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] px-6 py-5"
      aria-label="What fed this run"
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={`mt-[7px] h-2.5 w-2.5 flex-none rounded-full ${
            narrowed ? "bg-[#9a6b12]" : "bg-[var(--brand-teal-deep)]"
          }`}
        />
        <div className="min-w-0">
          <p className="font-[family-name:var(--font-display)] text-[16px] font-extrabold leading-snug text-[var(--text-primary)]">
            Ranked {findingsCount.toLocaleString()} findings from {formatDay(analysedFrom)} to{" "}
            {formatDay(analysedTo)}.
          </p>
          {narrowed ? (
            <p className="mt-1.5 max-w-[86ch] text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
              You asked for data through {formatDay(to)}. The newest Search Console day on
              record is {formatDay(analysedTo)}, so the run stops {shortBy}{" "}
              {shortBy === 1 ? "day" : "days"} short. Re-sync Search Console to widen it.
            </p>
          ) : (
            <p className="mt-1.5 text-[13.5px] text-[var(--text-secondary)]">
              The full range you asked for.
            </p>
          )}
        </div>
      </div>

      <dl className="mt-4 grid gap-x-8 gap-y-2 border-t border-[var(--border)] pt-4 sm:grid-cols-2">
        {Object.keys(data.readiness ?? {}).map((key) => {
          const through = data.source_freshness?.[key] ?? null;
          const behind = through ? daysBetween(through, to) : null;
          const stale = behind !== null && behind > 4;
          return (
            <div
              key={key}
              className="flex items-baseline justify-between gap-3 text-[13.5px]"
            >
              <dt className="text-[var(--text-secondary)]">{SOURCE_LABELS[key] ?? key}</dt>
              <dd
                className={
                  stale
                    ? "font-medium text-[#8a5e10]"
                    : "text-[var(--text-tertiary)]"
                }
              >
                through {formatDay(through)}
                {stale ? ` · ${behind} days behind` : ""}
              </dd>
            </div>
          );
        })}
      </dl>

      <p className="mt-3 max-w-[86ch] text-xs leading-relaxed text-[var(--text-tertiary)]">
        Dates are the newest row on record for each source, not the last time a sync reported
        success — a sync can return nothing and still say it worked.
      </p>
    </section>
  );
}
