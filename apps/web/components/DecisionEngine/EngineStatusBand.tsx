import { ReportedFindings } from "@/components/DecisionEngine/ReportedFindings";
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
  const actionCount = (data.growth_actions ?? []).length;
  // Counted off the findings the response already carries rather than
  // asked for separately, so these three can never add up to something
  // other than the total printed beside them.
  const findings = data.findings ?? [];
  const coreWorkCount = findings.filter((row) => row.core_work).length;
  // The findings themselves, so the count and the list cannot disagree:
  // everything that is neither offered nor already in the plan.
  const offered = new Set((data.growth_actions ?? []).map((row) => row.rule_key));
  const reported = findings.filter(
    (row) => !row.core_work && !offered.has(row.rule_key),
  );
  const reportedCount = reported.length;
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
            Checked {findingsCount.toLocaleString()}{" "}
            {findingsCount === 1 ? "thing" : "things"} on the site, {formatDay(analysedFrom)}{" "}
            to {formatDay(analysedTo)}.
          </p>

          {/* "Ranked 120 findings" was the whole sentence, and it accounted
              for two of them. The other 118 are not missing and they are not
              ranked — most are reported, some are already in the plan — and
              a reader who cannot see where they went reasonably assumes the
              engine lost them. */}
          <p className="mt-1.5 max-w-[86ch] text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
            {actionCount.toLocaleString()}{" "}
            {actionCount === 1 ? "is a growth action" : "are growth actions"} and
            {actionCount === 1 ? " is" : " are"} ranked above.
            {coreWorkCount > 0 ? (
              <>
                {" "}
                {coreWorkCount.toLocaleString()}{" "}
                {coreWorkCount === 1 ? "is" : "are"} core work your plan already
                covers.
              </>
            ) : null}
            {reportedCount > 0 ? (
              <>
                {" "}
                The remaining {reportedCount.toLocaleString()}{" "}
                {reportedCount === 1 ? "is" : "are"} reported rather than
                offered.
              </>
            ) : null}
          </p>

          {narrowed ? (
            <p className="mt-2 max-w-[86ch] text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
              Those dates are Search Console&rsquo;s. You asked through{" "}
              {formatDay(to)}; its newest day on record is {formatDay(analysedTo)},
              so the run stops {shortBy} {shortBy === 1 ? "day" : "days"} short.
              Each source&rsquo;s own last day is below. Re-sync Search Console to
              widen it.
            </p>
          ) : null}
        </div>
      </div>

      <ReportedFindings findings={reported} />

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
