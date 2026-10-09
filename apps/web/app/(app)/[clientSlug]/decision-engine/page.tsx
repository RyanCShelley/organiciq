import Link from "next/link";

import { ConstraintCard } from "@/components/DecisionEngine/ConstraintCard";
import { EmptySlotCard, SlotCard } from "@/components/DecisionEngine/SlotCard";
import { Alert } from "@/components/ui/Alert";
import { apiFetch } from "@/lib/api";
import { accountToolHref } from "@/lib/account-routes";
import { requireAccountClient } from "@/lib/account-routes.server";
import {
  BRANCH_LABEL,
  formatDay,
  monthName,
  type MonthlyRecord,
  type RunSummary,
} from "@/lib/monthly-record";
import { withNavContext } from "@/lib/navigation";

export default async function DecisionEnginePage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clientSlug } = await params;
  const query = await searchParams;
  const selectedClient = await requireAccountClient(clientSlug, "decision-engine");
  const clientId = selectedClient.id;
  const wanted = typeof query.run === "string" ? query.run : null;

  let runs: RunSummary[] = [];
  let record: MonthlyRecord | null = null;
  let error: string | null = null;

  try {
    runs = await apiFetch<RunSummary[]>("/decisions/records", { clientId });
    const month = wanted ?? runs[0]?.month;
    if (month) {
      record = await apiFetch<MonthlyRecord>(
        `/decisions/records/${encodeURIComponent(month)}`,
        { clientId },
      );
    }
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load the saved run";
  }

  // Content opportunities still works in date ranges, so it is handed the
  // window this run actually covered rather than a window nobody chose.
  const windowFrom = record ? `${record.month}-01` : "";
  const windowTo = record?.data_through ?? windowFrom;
  const contentOppHref = withNavContext(
    accountToolHref(selectedClient.slug, "content-opp"),
    clientId,
    windowFrom,
    windowTo,
  );

  if (error) {
    return (
      <section>
        <h1 className="font-[family-name:var(--font-display)] text-[30px] font-black tracking-[-0.02em]">
          Decision engine
        </h1>
        <Alert variant="danger" className="mt-4">
          {error}
        </Alert>
      </section>
    );
  }

  if (!record) {
    return (
      <section>
        <h1 className="font-[family-name:var(--font-display)] text-[30px] font-black tracking-[-0.02em]">
          Decision engine
        </h1>
        <p className="mt-3 max-w-[70ch] text-[14.5px] leading-relaxed text-[var(--text-secondary)]">
          No saved run for {selectedClient.client_name ?? selectedClient.slug} yet.
          The engine runs monthly and saves a record; this page renders it rather
          than recomputing, so there is nothing to show until the first run.
        </p>
      </section>
    );
  }

  const withheld = record.constraint === "withheld";
  const assignable = record.actions.length + record.incidents.length;

  return (
    <section className="space-y-[var(--section-gap)]">
      {/* The run is a saved thing with a date, not a window somebody picked.
          The date picker that stood here invited a reader to ask for a range
          the engine never ran, and then recomputed one on the spot. */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-[30px] font-black leading-tight tracking-[-0.02em] text-[var(--text-primary)]">
            Decision engine
          </h1>
          <p className="mt-1.5 text-[13.5px] text-[var(--text-secondary)]">
            {monthName(record.month)} run · saved {formatDay(record.run_saved_at)} from
            data through {formatDay(record.data_through)}
          </p>
        </div>

        {runs.length > 1 ? (
          <nav aria-label="Saved runs" className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] text-[var(--text-tertiary)]">Run</span>
            {runs.slice(0, 6).map((run) => (
              <Link
                key={run.month}
                href={`?run=${run.month}`}
                aria-current={run.month === record.month ? "page" : undefined}
                className={`min-h-[36px] rounded-lg border px-3 py-1.5 text-[13px] no-underline ${
                  run.month === record.month
                    ? "border-[var(--brand-teal-deep)] font-semibold text-[var(--text-primary)]"
                    : "border-[var(--border)] text-[var(--text-secondary)]"
                }`}
              >
                {monthName(run.month)}
              </Link>
            ))}
          </nav>
        ) : null}
      </div>

      <ConstraintCard record={record} />

      {withheld ? (
        <Alert variant="danger">
          Nothing is prescribed this month. {record.reason_text}
        </Alert>
      ) : (
        <>
          <section aria-labelledby="plan-heading" className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2
                id="plan-heading"
                className="font-[family-name:var(--font-display)] text-[18px] font-extrabold text-[var(--text-primary)]"
              >
                Growth actions to assign
              </h2>
              {/* One rule, stated once. The old screen had three orderings
                  on the same page and told the reader none of them was
                  binding. */}
              <p className="text-[13px] text-[var(--text-secondary)]">
                <span className="capitalize">{record.plan}</span> plan:{" "}
                {record.action_slots}{" "}
                {record.action_slots === 1 ? "slot" : "slots"}, filled from the
                constraint. Leftovers go to the next failing branch.
              </p>
            </div>

            {record.actions.map((action) => (
              <SlotCard key={action.action_uid} action={action} />
            ))}
            {record.empty_slots.map((slot) => (
              <EmptySlotCard key={slot.slot} slot={slot.slot} reason={slot.reason} />
            ))}

            {assignable === 0 && record.empty_slots.length === 0 ? (
              <p className="text-[14px] text-[var(--text-secondary)]">
                No action qualified this month.
              </p>
            ) : null}
          </section>

          {record.not_this_month.length > 0 ? (
            <section
              aria-labelledby="later-heading"
              className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] px-6 py-5"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <h2
                  id="later-heading"
                  className="font-[family-name:var(--font-display)] text-[16px] font-extrabold text-[var(--text-primary)]"
                >
                  Not this month
                </h2>
                <p className="text-[13px] text-[var(--text-tertiary)]">
                  Kept for when its branch fails or a slot opens
                </p>
              </div>
              <ul className="mt-2">
                {record.not_this_month.slice(0, 25).map((item, index) => (
                  <li
                    key={`${item.id}-${item.target_url}-${index}`}
                    className="border-t border-[var(--border)] py-3"
                  >
                    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                      <span className="min-w-0 flex-1 text-[14px] font-semibold text-[var(--text-primary)]">
                        {item.title}
                      </span>
                      {item.branch ? (
                        <span className="whitespace-nowrap rounded-full bg-[#E9EEF8] px-2.5 py-0.5 text-[11.5px] font-semibold text-[#2C4A86]">
                          {BRANCH_LABEL[item.branch] ?? item.branch} ·{" "}
                          {item.branch_status}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-0.5 text-[13px] text-[var(--text-secondary)]">
                      {item.reason}
                    </p>
                  </li>
                ))}
              </ul>
              {record.not_this_month.length > 25 ? (
                <p className="mt-2 text-[13px] text-[var(--text-tertiary)]">
                  and {record.not_this_month.length - 25} more
                </p>
              ) : null}
            </section>
          ) : null}
        </>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <section
          aria-labelledby="results-heading"
          className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] px-6 py-5"
        >
          <h2
            id="results-heading"
            className="font-[family-name:var(--font-display)] text-[16px] font-extrabold text-[var(--text-primary)]"
          >
            Last month&rsquo;s results
          </h2>
          <p className="mt-1 text-[13px] leading-relaxed text-[var(--text-secondary)]">
            Each action is checked 28 to 45 days after it ships, on the metric it
            was meant to move.
          </p>
          {record.previous_results.length === 0 ? (
            <p className="mt-3 text-[13px] text-[var(--text-tertiary)]">
              Nothing logged yet. Results appear after the first check date.
            </p>
          ) : (
            <ul className="mt-3 space-y-2 text-[13px]">
              {record.previous_results.map((row, index) => (
                <li key={`${row.action_uid}-${index}`} className="flex justify-between gap-3">
                  <span className="min-w-0 flex-1">{row.title}</span>
                  <span className="tabular-nums text-[var(--text-secondary)]">
                    {row.before ?? "—"} → {row.after ?? "—"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section
          aria-labelledby="gaps-heading"
          className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] px-6 py-5"
        >
          <h2
            id="gaps-heading"
            className="font-[family-name:var(--font-display)] text-[16px] font-extrabold text-[var(--text-primary)]"
          >
            Data that limited this run
          </h2>
          <p className="mt-1 text-[13px] leading-relaxed text-[var(--text-secondary)]">
            Rules needing these did not fire. Fixing them raises confidence.
          </p>
          {record.data_gaps.length === 0 ? (
            <p className="mt-3 text-[13px] text-[var(--text-tertiary)]">
              Nothing was missing.
            </p>
          ) : (
            <ul className="mt-3 flex flex-wrap gap-2">
              {record.data_gaps.map((gap) => (
                <li
                  key={gap.input}
                  className="rounded-full bg-[#FDF1E3] px-3 py-1 text-[12px] font-medium text-[#8A4B08]"
                >
                  {gap.input}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <Link
        href={contentOppHref}
        className="inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-5 text-[13.5px] font-semibold no-underline"
      >
        See content opportunities
      </Link>
    </section>
  );
}
