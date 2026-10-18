import { dataGapGuidance } from "@/lib/data-gap-guidance";
import { TriangleAlert } from "lucide-react";
import Link from "next/link";

import {
  ConstraintCard,
  type SlotProgress,
} from "@/components/DecisionEngine/ConstraintCard";
import { HistoricalRuns } from "@/components/DecisionEngine/HistoricalRuns";
import { RunEngineButton } from "@/components/DecisionEngine/RunEngineButton";
import { PlanReviewState, ApprovedWork } from "@/components/DecisionEngine/PlanReviewState";
import { MonthlyReviewOverview } from "@/components/DecisionEngine/MonthlyReviewOverview";
import { PlanReviewPanel } from "@/components/DecisionEngine/PlanReviewPanel";
import { actionCount, type PlanReview } from "@/lib/plan-review";
import { WatchlistPanel, type WatchItem } from "@/components/DecisionEngine/WatchlistPanel";
import { SlotActionBar } from "@/components/DecisionEngine/SlotActionBar";
import { EmptySlotCard, SlotCard } from "@/components/DecisionEngine/SlotCard";
import { Alert } from "@/components/ui/Alert";
import { apiFetch } from "@/lib/api";
import { accountToolHref } from "@/lib/account-routes";
import { requireAccountClient } from "@/lib/account-routes.server";
import {
  BRANCH_LABEL,
  finishedRuns,
  formatDay,
  monthName,
  nextMonth,
  previousMonth,
  type Assignee,
  type Candidate,
  type MonthlyRecord,
  type RunSummary,
  type SlotState,
  type Workflow,
} from "@/lib/monthly-record";
import { PreviousResults } from "@/components/DecisionEngine/PreviousResults";
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
  const now = new Date();
  const currentMonth = `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}`;

  let runs: RunSummary[] = [];
  let record: MonthlyRecord | null = null;
  let error: string | null = null;

  // Re-running replaces a saved record, so it stays an admin action. The API
  // enforces it; this only decides whether the button is drawn, because a
  // button that always 403s is worse than no button.
  //
  // Started now and awaited below: the role and the people list do not depend on
  // the record, so they were waiting behind it for no reason.
  const canRunPromise = apiFetch<{ role: string }>("/auth/me", { clientId })
    .then((me) => me.role === "sma_admin")
    .catch(() => false);
  const assigneesPromise = apiFetch<Assignee[]>("/decisions/assignees", { clientId }).then(
    (people) => ({ ok: true as const, people }),
    () => ({ ok: false as const, people: [] as Assignee[] }),
  );

  try {
    runs = finishedRuns(
      await apiFetch<RunSummary[]>("/decisions/records", { clientId }),
      currentMonth,
    );
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

  const canRun = await canRunPromise;
  const review = record ? await apiFetch<PlanReview>(
    `/decisions/records/${encodeURIComponent(record.month)}/review`, { clientId },
  ).catch(() => null) : null;
  const measurementSettings = await apiFetch<{ target_lead_rate_pct: number | null; conversion_page_count: number }>("/decisions/measurement-settings", { clientId }).catch(() => null);
  const watchlist = await apiFetch<WatchItem[]>("/decisions/watchlist", { clientId }).catch(() => null);

  // The workflow is fetched apart from the record for the same reason it is
  // stored apart: assigning a task must not be able to change what the engine
  // decided. A failure here leaves the plan readable and the buttons inert,
  // which is the right way round.
  let slotStates = new Map<string, SlotState>();
  let assignees: Assignee[] = [];
  let teamworkReady = false;
  if (record) {
    try {
      const [workflow, people] = await Promise.all([
        apiFetch<Workflow>(
          `/decisions/records/${encodeURIComponent(record.month)}/workflow`,
          { clientId },
        ),
        assigneesPromise,
      ]);
      // Both or neither, as before: a workflow without the people to assign
      // it to would draw buttons that cannot work.
      if (!people.ok) throw new Error("assignees unavailable");
      slotStates = new Map(workflow.actions.map((row) => [row.uid, row]));
      teamworkReady = workflow.teamwork_ready;
      assignees = people.people;
    } catch {
      // Leave the plan readable.
    }
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
        <Alert variant="danger">
          {error}
        </Alert>
      </section>
    );
  }

  if (!record) {
    return (
      <section>
        <p className="max-w-[70ch] text-[14.5px] leading-relaxed text-[var(--text-secondary)]">
          No saved run for {selectedClient.client_name ?? selectedClient.slug} yet.
          The engine reads a whole finished month and saves a record, and that record is
          the plan for the month after. It runs on the {5}th for the month before; this
          page renders the saved run rather than recomputing it.
        </p>
        {canRun ? (
          <div className="mt-4 flex">
            <RunEngineButton
              clientId={clientId}
              slug={selectedClient.slug}
              month={previousMonth(currentMonth)}
              currentMonth={currentMonth}
            />
          </div>
        ) : null}
      </section>
    );
  }

  // The plan is the engine's ranking unless somebody said otherwise. An
  // action taken out drops off; one added joins the end, because a slot
  // number belongs to the engine's ordering and this is not that.
  const candidates: Candidate[] = record.candidates ?? [];
  const engineChose = new Set(
    candidates.filter((c) => c.slot !== null).map((c) => c.action_uid),
  );
  const planned = candidates.filter((c) => {
    const override = slotStates.get(c.action_uid)?.in_plan;
    return override ?? engineChose.has(c.action_uid);
  });
  // Fall back to the saved actions for a record written before candidates
  // were stored, so an older month still renders its plan.
  const actions = record.plan_review ? record.actions : candidates.length ? planned : record.actions;
  const added = planned.filter((c) => !engineChose.has(c.action_uid)).length;
  const removed = candidates.filter(
    (c) => engineChose.has(c.action_uid) && slotStates.get(c.action_uid)?.in_plan === false,
  ).length;

  // Counted from what the team did, not from what the engine prescribed:
  // five filled slots nobody owns is not five slots of progress.
  const weighted = (statuses: string[]) => actions.filter(a => statuses.includes(slotStates.get(a.action_uid)?.status ?? "")).reduce((n, a) => n + (record.plan_review ? actionCount([a]) : 1), 0);
  const progress: SlotProgress = {
    total: record.action_slots,
    filled: record.plan_review ? actionCount(actions) : actions.length,
    assigned: weighted(["assigned", "done"]),
    skipped: weighted(["skipped"]),
  };

  const withheld = record.constraint === "withheld";
  const assignable = record.actions.length + record.incidents.length;

  return (
    <PlanReviewState key={`${record.month}-${review?.revision ?? 0}`}><section className="space-y-[var(--section-gap)]">
      {/* The run is a saved thing with a date, not a window somebody picked.
          It reads a whole finished month and is the plan for the month after,
          so the title block says both. The page title is already in the top bar. */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-[22px] font-extrabold leading-tight tracking-[-0.01em] text-[var(--text-primary)]">
            Plan for {monthName(nextMonth(record.month))}
          </h2>
          <p className="mt-1.5 text-[13.5px] text-[var(--text-secondary)]">
            Run on {monthName(record.month)} data · saved {formatDay(record.run_saved_at)} from
            data through {formatDay(record.data_through)}
          </p>
        </div>

        <details className="text-sm"><summary className="cursor-pointer">Assessment history & controls</summary><div className="mt-3 flex flex-wrap items-center gap-4">
          {runs.length > 1 ? (
            <HistoricalRuns slug={selectedClient.slug} runs={runs} selected={record.month} />
          ) : null}
          {canRun ? (
            <RunEngineButton
              clientId={clientId}
              slug={selectedClient.slug}
              month={record.month}
              currentMonth={currentMonth}
            />
          ) : null}
        </div></details>
      </div>

      <MonthlyReviewOverview record={record} targetRate={measurementSettings?.target_lead_rate_pct ?? null} suggestedFocus={review?.suggested_focus ?? record.engine_constraint ?? record.constraint} />
      <details className="rounded-lg border border-[var(--border)] p-4 text-sm"><summary className="cursor-pointer font-semibold">Explore the evidence · keywords, channels, lead rate and calculation details</summary><div className="mt-4">
      <ConstraintCard record={record} progress={progress} measurementSettings={measurementSettings ? { clientId, slug: selectedClient.slug, target: measurementSettings.target_lead_rate_pct } : undefined} />
      </div></details>
      {review ? <PlanReviewPanel key={`${record.month}-${review.revision}`} initial={review} lockedUids={actions.filter(a => { const state = slotStates.get(a.action_uid); return Boolean(state?.assignee_email || state?.sent_at || state?.shipped_on); }).map(a => a.action_uid)} clientId={clientId} slug={selectedClient.slug} month={record.month} /> : <Alert variant="danger">Plan review could not load. Reload before editing this plan.</Alert>}

      {/* Above the plan, because a plan read as if the site were working is
          worse than no plan. An incident takes no slot and does not change
          the constraint — it is a fault, not a growth action. */}
      {record.incidents.length > 0 ? (
        <section aria-labelledby="incidents-heading" className="space-y-3">
          <h2
            id="incidents-heading"
            className="font-[family-name:var(--font-display)] text-[18px] font-extrabold text-[var(--text-primary)]"
          >
            Check before anything else
          </h2>
          {record.incidents.map((incident) => (
            <article
              key={incident.incident_uid}
              className="rounded-[var(--radius-lg,14px)] border-2 border-[#E3B25C] bg-[#FFF8E6] px-6 py-5"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[#F5D58A] px-2.5 py-0.5 text-[11.5px] font-semibold text-[#6B4A00]">
                  <TriangleAlert className="h-3.5 w-3.5" aria-hidden />
                  Caution
                </span>
                <span className="text-[11.5px] font-semibold text-[#8A4B08]">
                  {incident.scope} · no slot used
                </span>
              </div>
              <h3 className="mt-1.5 font-[family-name:var(--font-display)] text-[17px] font-extrabold leading-snug text-[var(--text-primary)]">
                {incident.title}
              </h3>
              {incident.detail ? (
                <p className="mt-1 max-w-[80ch] text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
                  {incident.detail}
                </p>
              ) : null}
              {incident.evidence?.length ? (
                <ul className="mt-2 space-y-0.5">
                  {incident.evidence.map((line) => (
                    <li
                      key={line}
                      className="font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]"
                    >
                      {line}
                    </li>
                  ))}
                </ul>
              ) : null}
            </article>
          ))}
        </section>
      ) : null}

      {withheld ? (
        <Alert variant="danger">
          Nothing is prescribed this month. {record.reason_text}
        </Alert>
      ) : record.plan_review?.approved_at ? (
        <ApprovedWork><details className="rounded-xl border border-[var(--border)] p-5"><summary className="cursor-pointer font-semibold">Approved work · assignment and Teamwork</summary><div className="mt-4 space-y-4">
          <section aria-labelledby="plan-heading" className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2
                id="plan-heading"
                className="font-[family-name:var(--font-display)] text-[18px] font-extrabold text-[var(--text-primary)]"
              >
                4. Assign and send to Teamwork
              </h2>
              {/* One rule, stated once. The old screen had three orderings
                  on the same page and told the reader none of them was
                  binding. */}
              <p className="text-[13px] text-[var(--text-secondary)]">
                <span className="capitalize">{record.plan}</span> plan:{" "}
                {record.action_slots}{" "}
                {record.action_slots === 1 ? "action" : "actions"}. Your selected work is ready for assignment and delivery.
                {added || removed ? (
                  <span className="ml-1 font-semibold text-[var(--text-primary)]">
                    {added ? `${added} added` : ""}
                    {added && removed ? ", " : ""}
                    {removed ? `${removed} taken out` : ""} by you.
                  </span>
                ) : null}
              </p>
            </div>

            {actions.map((action) => (
              <SlotCard
                key={action.action_uid}
                action={action}
                status={slotStates.get(action.action_uid)?.status}
              >
                <SlotActionBar
                  action={action}
                  state={slotStates.get(action.action_uid)}
                  assignees={assignees}
                  clientId={clientId}
                  slug={selectedClient.slug}
                  month={record.month}
                  teamworkReady={teamworkReady}
                  approved={Boolean(record.plan_review?.approved_at)}
                />
              </SlotCard>
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
                  Kept for when its branch becomes the focus or a slot opens
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
        </div></details></ApprovedWork>
      ) : null}

      <details className="rounded-lg border border-[var(--border)] p-4 text-sm"><summary className="cursor-pointer font-semibold">Supporting information · targets, previous results and data gaps</summary><div className="mt-4 space-y-5">
      {watchlist ? <WatchlistPanel initial={watchlist} clientId={clientId} slug={selectedClient.slug} /> : <Alert variant="danger">Watchlist could not load.</Alert>}

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
            Approved work is checked after its recorded shipment and chosen waiting period.
            Manual verification stays separate from automated metric checks.
          </p>
          <PreviousResults
            rows={record.previous_results.filter(
              (row) => !row.kind || row.kind === "action",
            )}
            empty="Nothing logged yet. Results appear after the first check date."
          />
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
            These limits describe the saved assessment. Current setup is checked separately below; rerun the assessment to use changed settings. History and reference limits do not mean the site needs fixing.
          </p>
          {record.data_gaps.length === 0 ? (
            <p className="mt-3 text-[13px] text-[var(--text-tertiary)]">
              Nothing was missing.
            </p>
          ) : (
            <ul className="mt-3 space-y-3">
              {record.data_gaps.map(gap => {
                const guidance = dataGapGuidance(gap.input, measurementSettings ?? undefined);
                return <li key={gap.input} className="rounded-lg border border-[var(--border)] p-3 text-sm">
                  <p className="font-semibold">{guidance.title} <span className="text-xs font-normal text-[var(--text-secondary)]">· {guidance.kind}</span></p>
                  <p className="mt-1 text-[var(--text-secondary)]">{guidance.next}</p>
                  {guidance.tool && <Link className="mt-2 inline-block underline" href={guidance.tool === "client" ? `/clients/${selectedClient.slug}` : `/${selectedClient.slug}/watch-list`}>{guidance.tool === "client" ? "Open client setup" : "Open Watch List"}</Link>}
                </li>;
              })}
            </ul>
          )}
        </section>
      </div>

      </div></details>
      <Link
        href={contentOppHref}
        className="inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-5 text-[13.5px] font-semibold no-underline"
      >
        See content opportunities
      </Link>
    </section></PlanReviewState>
  );
}
