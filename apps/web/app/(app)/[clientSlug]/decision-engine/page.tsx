import { TriangleAlert } from "lucide-react";
import Link from "next/link";

import { HistoricalRuns } from "@/components/DecisionEngine/HistoricalRuns";
import { RunEngineButton } from "@/components/DecisionEngine/RunEngineButton";
import { PlanReviewState } from "@/components/DecisionEngine/PlanReviewState";
import { MonthlyReviewOverview } from "@/components/DecisionEngine/MonthlyReviewOverview";
import { PlanReviewPanel } from "@/components/DecisionEngine/PlanReviewPanel";
import { type PlanReview } from "@/lib/plan-review";
import { Alert } from "@/components/ui/Alert";
import { apiFetch } from "@/lib/api";
import { requireAccountClient } from "@/lib/account-routes.server";
import {
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

export default async function DecisionEnginePage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clientSlug } = await params;
  const query = await searchParams;
  const selectedClient = await requireAccountClient(
    clientSlug,
    "decision-engine",
  );
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
  const assigneesPromise = apiFetch<Assignee[]>("/decisions/assignees", {
    clientId,
  }).then(
    (people) => ({ ok: true as const, people }),
    () => ({ ok: false as const, people: [] as Assignee[] }),
  );

  try {
    runs = finishedRuns(
      await apiFetch<RunSummary[]>("/decisions/records", { clientId }),
      currentMonth,
    );
    const month = wanted ?? runs[0]?.month;
    if (month && runs.some((run) => run.month === month)) {
      record = await apiFetch<MonthlyRecord>(
        `/decisions/records/${encodeURIComponent(month)}`,
        { clientId },
      );
    }
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load the saved run";
  }

  const canRun = await canRunPromise;
  const review = record
    ? await apiFetch<PlanReview>(
        `/decisions/records/${encodeURIComponent(record.month)}/review`,
        { clientId },
      ).catch(() => null)
    : null;
  const measurementSettings = await apiFetch<{
    target_lead_rate_pct: number | null;
    conversion_page_count: number;
  }>("/decisions/measurement-settings", { clientId }).catch(() => null);

  // The workflow is fetched apart from the record for the same reason it is
  // stored apart: assigning a task must not be able to change what the engine
  // decided. A failure here leaves the plan readable and the buttons inert,
  // which is the right way round.
  let slotStates = new Map<string, SlotState>();
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
    } catch {
      // Leave the plan readable.
    }
  }

  if (error) {
    return (
      <section>
        <Alert variant="danger">{error}</Alert>
      </section>
    );
  }

  if (!record) {
    return (
      <section>
        <p className="max-w-[70ch] text-[14.5px] leading-relaxed text-[var(--text-secondary)]">
          No saved run for {selectedClient.client_name ?? selectedClient.slug}{" "}
          yet. The engine reads a whole finished month and saves a record, and
          that record is the plan for the month after. It runs on the {5}th for
          the month before; this page renders the saved run rather than
          recomputing it.
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
  const actions = record.plan_review
    ? record.actions
    : candidates.length
      ? planned
      : record.actions;

  const withheld = record.constraint === "withheld";

  return (
    <PlanReviewState key={`${record.month}-${review?.revision ?? 0}`}>
      <section className="space-y-[var(--section-gap)]">
        {/* The run is a saved thing with a date, not a window somebody picked.
          It reads a whole finished month and is the plan for the month after,
          so the title block says both. The page title is already in the top bar. */}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="font-[family-name:var(--font-display)] text-[22px] font-extrabold leading-tight tracking-[-0.01em] text-[var(--text-primary)]">
              Reviewing {monthName(record.month)} · Planning{" "}
              {monthName(nextMonth(record.month))}
            </h2>
            <p className="mt-1.5 text-[13.5px] text-[var(--text-secondary)]">
              Run on {monthName(record.month)} data · saved{" "}
              {formatDay(record.run_saved_at)} from data through{" "}
              {formatDay(record.data_through)}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            {runs.length > 1 ? (
              <HistoricalRuns
                slug={selectedClient.slug}
                runs={runs}
                selected={record.month}
              />
            ) : null}
            {canRun ? (
              <RunEngineButton
                clientId={clientId}
                slug={selectedClient.slug}
                month={record.month}
                currentMonth={currentMonth}
              />
            ) : null}
          </div>
        </div>

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

        {(record.recommendation_version ?? 1) < 3 ? (
          <Alert variant="warning">
            These recommendations were saved under earlier rules. Re-run this
            month’s assessment using Run assessment before choosing new work.
            Updated rules check traffic, offer fit and crawl evidence, and
            exclude exact-phrase-only title tasks. Existing approved work stays
            in its history.
          </Alert>
        ) : null}
        <MonthlyReviewOverview
          record={record}
          targetRate={measurementSettings?.target_lead_rate_pct ?? null}
          suggestedFocus={
            review?.suggested_focus ??
            record.engine_constraint ??
            record.constraint
          }
          suggestedReason={review?.suggested_reason}
          capacity={review?.capacity}
        />
        {review ? (
          <PlanReviewPanel
            key={`${record.month}-${record.run_saved_at}-${review.revision}`}
            initial={review}
            lockedUids={actions
              .filter((a) => {
                const state = slotStates.get(a.action_uid);
                return Boolean(
                  state?.assignee_email || state?.sent_at || state?.shipped_on,
                );
              })
              .map((a) => a.action_uid)}
            clientId={clientId}
            slug={selectedClient.slug}
            month={record.month}
          />
        ) : (
          <Alert variant="danger">
            Plan review could not load. Reload before editing this plan.
          </Alert>
        )}

        {withheld ? (
          <Alert variant="danger">
            No work is prescribed. {record.reason_text}
          </Alert>
        ) : record.plan_review?.approved_at ? (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
            <p>Approved work is ready in Work &amp; Results.</p>
            <Link
              className="mt-2 inline-block text-[var(--brand-teal)] underline"
              href={`/${selectedClient.slug}/annotations?${new URLSearchParams({ from: typeof query.from === "string" ? query.from : `${record.month}-01`, to: typeof query.to === "string" ? query.to : (record.data_through?.slice(0, 10) ?? `${record.month}-28`), range: "custom" })}`}
            >
              Assign and follow work →
            </Link>
          </div>
        ) : null}
      </section>
    </PlanReviewState>
  );
}
