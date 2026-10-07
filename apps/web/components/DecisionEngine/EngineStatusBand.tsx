import { SOURCE_LABELS, staleSources, type DiagnoseResponse } from "@/lib/decision-engine";

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

/**
 * One line about the run, with the per-source detail behind a disclosure.
 *
 * This replaces three displays that competed to say the same thing: a row
 * of readiness badges, a grid of lever cards, and a summary strip of
 * counts. None of them answered the question someone actually has when
 * the numbers look wrong — how current is the data underneath — because
 * readiness was a boolean. A source that stopped a fortnight ago reported
 * as a green badge.
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
  const stale = staleSources(data, to);
  const window = `${formatDay(data.analysis_from ?? from)} – ${formatDay(data.analysis_to ?? to)}`;

  return (
    <section className="workspace-panel" aria-label="Engine status">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="mt-[7px] h-2.5 w-2.5 flex-none rounded-full bg-[var(--brand-teal-deep)]"
        />
        <div className="min-w-0">
          <p className="font-[family-name:var(--font-display)] text-[17px] font-extrabold leading-snug text-[var(--text-primary)]">
            All four sources reported. Ranking {findingsCount.toLocaleString()} findings from{" "}
            {window}.
          </p>
        </div>
      </div>

      <details className="mt-4 border-t border-[var(--border)] pt-3">
        <summary className="flex min-h-[44px] cursor-pointer items-center text-[13.5px] font-semibold text-[var(--brand-teal-deep)]">
          What fed this run
        </summary>
        <dl className="mt-3 grid gap-x-7 gap-y-2 sm:grid-cols-2">
          {Object.entries(data.readiness).map(([key]) => (
            <div
              key={key}
              className="flex items-baseline justify-between gap-3 border-b border-[var(--border-subtle,var(--border))] pb-2 text-[13.5px]"
            >
              <dt className="text-[var(--text-secondary)]">{SOURCE_LABELS[key] ?? key}</dt>
              <dd className="text-[var(--text-tertiary)]">
                through {formatDay(data.source_freshness?.[key])}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 max-w-[80ch] text-xs leading-relaxed text-[var(--text-tertiary)]">
          A score built from a partial set is not comparable to a full one, so the engine stops
          until every source reports.
        </p>
      </details>

      {stale.length > 0 ? (
        <div className="mt-4 rounded-[10px] border border-[var(--warning-border,#e8d6ae)] bg-[var(--warning-soft,#fff8ec)] p-4">
          <p className="text-[14.5px] font-semibold leading-snug text-[var(--text-primary)]">
            {stale.length === 1
              ? `${SOURCE_LABELS[stale[0].key] ?? stale[0].key} facts stop on ${formatDay(stale[0].through)}, ${stale[0].daysBehind} days behind the rest of this run.`
              : `${stale.length} sources are behind the rest of this run.`}
          </p>
          <p className="mt-1.5 max-w-[86ch] text-[13px] leading-relaxed text-[var(--text-secondary)]">
            Rules that read{" "}
            {stale.map((row) => SOURCE_LABELS[row.key] ?? row.key).join(" and ")} are measured over
            the shorter window and will read low until it catches up.
          </p>
        </div>
      ) : null}
    </section>
  );
}
