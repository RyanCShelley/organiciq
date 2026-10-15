import Link from "next/link";

import { CandidateTable } from "@/components/DecisionEngine/CandidateTable";
import { SlotActionBar } from "@/components/DecisionEngine/SlotActionBar";
import { EmptySlotCard, SlotCard } from "@/components/DecisionEngine/SlotCard";
import { PoolSummary } from "@/components/DecisionEngine/PoolSummary";
import { PreviousResults } from "@/components/DecisionEngine/PreviousResults";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch } from "@/lib/api";
import { accountToolHref } from "@/lib/account-routes";
import { requireAccountClient } from "@/lib/account-routes.server";
import type {
  Assignee,
  MonthlyRecord,
  SlotState,
  Workflow,
} from "@/lib/monthly-record";

type RunSummary = { month: string };

/**
 * The retainer plan.
 *
 * The Decision Engine plans growth actions, which sit outside the monthly
 * fee. This plans the work that is inside it: refreshing content that is
 * losing ground, and writing the pages a tracked term has none for. Two
 * allowances, two pools, one machine — the cards,
 * assignment, the Teamwork send and the results loop are the same ones,
 * so a refresh is handed over exactly as a growth action is.
 */
export default async function ContentOppPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clientSlug } = await params;
  const query = await searchParams;
  const client = await requireAccountClient(clientSlug, "content-opp");
  const clientId = client.id;

  let record: MonthlyRecord | null = null;
  let recordError: string | null = null;
  // Started now: the people list does not depend on the record, so it was
  // waiting behind two round trips it had nothing to do with.
  const assigneesPromise = apiFetch<Assignee[]>("/decisions/assignees", { clientId }).then(
    (people) => ({ ok: true as const, people }),
    () => ({ ok: false as const, people: [] as Assignee[] }),
  );
  try {
    const runs = await apiFetch<RunSummary[]>("/decisions/records", { clientId });
    const month = typeof query.run === "string" ? query.run : runs[0]?.month;
    if (month) {
      record = await apiFetch<MonthlyRecord>(
        `/decisions/records/${encodeURIComponent(month)}`,
        { clientId },
      );
    }
  } catch (e) {
    recordError = e instanceof Error ? e.message : "Failed to load the saved run";
  }

  // Fetched apart from the record for the same reason it is stored apart:
  // assigning a task must not be able to change what the engine decided.
  // A failure here leaves the plan readable and the buttons inert.
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
      // Both or neither, as before.
      if (!people.ok) throw new Error("assignees unavailable");
      slotStates = new Map(workflow.actions.map((row) => [row.uid, row]));
      teamworkReady = workflow.teamwork_ready;
      assignees = people.people;
    } catch {
      // Leave the plan readable.
    }
  }

  // A record saved before the refresh plan existed carries no `updates`
  // key at all. That is not the same as a plan with no refreshes in it,
  // and saying so sent somebody to check an allowance that was fine.
  const planned = record != null && record.updates !== undefined;
  const updates = record?.updates ?? [];
  const emptyUpdates = record?.empty_update_slots ?? [];
  const slots = record?.update_slots ?? 0;
  // Everything the engine weighed and could not fit. The bulk of what it
  // found lives here, and a plan you cannot argue with is not a plan.
  const alsoFound = (record?.update_candidates ?? [])
    .filter((row) => row.slot === null)
    // The column shows the score, so the table is ordered by it. The plan is
    // filled by loss, and the two differ for a page whose action is not a
    // refresh.
    .sort((a, b) => b.score - a.score);

  // New pages. Same absence-of-key rule as above: an older record has no
  // `new_content` at all, which is not a plan that found nothing to write.
  const contentPlanned = record != null && record.new_content !== undefined;
  const newContent = record?.new_content ?? [];
  const emptyContent = record?.empty_content_slots ?? [];
  const contentSlots = record?.content_slots ?? 0;
  const scan = record?.content_scan;
  const contentAlsoFound = (record?.content_candidates ?? []).filter(
    (row) => row.slot === null,
  );
  const retainerResults = (record?.previous_results ?? []).filter(
    (row) => row.kind === "update" || row.kind === "content",
  );

  function renderPool(
    actions: NonNullable<MonthlyRecord["updates"]>,
    empty: { slot: number; reason: string }[],
    anchorPrefix: string,
  ) {
    return (
      <div className="space-y-3">
        {actions.map((action) => (
          <div key={action.action_uid} id={`${anchorPrefix}-${action.slot}`} className="scroll-mt-24">
          <SlotCard
            action={action}
            status={slotStates.get(action.action_uid)?.status}
          >
            <SlotActionBar
              action={action}
              state={slotStates.get(action.action_uid)}
              assignees={assignees}
              clientId={clientId}
              slug={client.slug}
              month={record!.month}
              teamworkReady={teamworkReady}
            />
          </SlotCard>
          </div>
        ))}
        {/* Slots empty for the same reason are one fact, not eight. */}
        {empty.length > 1 && empty.every((slot) => slot.reason === empty[0].reason) ? (
          <EmptySlotCard
            slot={`${empty[0].slot}–${empty[empty.length - 1].slot}`}
            reason={empty[0].reason}
          />
        ) : (
          empty.map((slot) => (
            <EmptySlotCard key={slot.slot} slot={slot.slot} reason={slot.reason} />
          ))
        )}
      </div>
    );
  }

  return (
    <section>
      {recordError ? <Alert variant="danger">{recordError}</Alert> : null}

      <section className="workspace-section">
        <SectionHeader
          title="Content refresh"
          description="Pages losing ground, ranked by the impressions they used to draw and no longer do. This is retainer work — it is inside the monthly fee, which is why it has its own allowance and does not compete with growth actions."
          actions={
            record ? (
              <span className="text-xs text-[var(--text-tertiary)]">{record.month}</span>
            ) : null
          }
        />

        {!record ? (
          <Alert variant="info">
            No saved run yet. The month is planned on the{" "}
            <Link
              href={accountToolHref(client.slug, "decision-engine")}
              className="underline"
            >
              Decision Engine
            </Link>
            , and the refresh plan is built in the same run.
          </Alert>
        ) : null}

        {record && !planned ? (
          <Alert variant="warning">
            This run was saved before the refresh plan existed, so it has
            none in it. Re-run {record.month} on the{" "}
            <Link
              href={accountToolHref(client.slug, "decision-engine")}
              className="underline"
            >
              Decision Engine
            </Link>{" "}
            to build one.
          </Alert>
        ) : null}

        {planned && slots === 0 && updates.length === 0 ? (
          <Alert variant="info">
            {emptyUpdates[0]?.reason ??
              `The ${record!.plan} plan includes no content refreshes.`}
          </Alert>
        ) : null}

        {planned ? (
          <div className="mb-4">
            <PoolSummary
              filled={updates}
              slots={slots}
              weighed={(record?.update_candidates ?? []).length || updates.length + alsoFound.length}
              statusOf={(uid) => slotStates.get(uid)?.status}
              anchorPrefix="refresh-slot"
              noun="refresh"
            />
          </div>
        ) : null}

        {renderPool(updates, emptyUpdates, "refresh-slot")}
      </section>

      {/* Parked for now: new pages for tracked terms only cover terms somebody
          already tracks, which is not the gap analysis this is meant to be.
          The record still carries the pool; the page shows it once it has
          something in it. */}
      {newContent.length > 0 || contentAlsoFound.length > 0 ? (
        <>
      <section className="workspace-section">
        <SectionHeader
          title="New content"
          description="Pages for tracked terms the site has no page about. A term only counts when the crawl shows no page carrying its words in the title, URL or headings, so a page that exists but is not ranking is never told to be written again."
          actions={
            record ? (
              <span className="text-xs text-[var(--text-tertiary)]">
                {record.month} · {newContent.length} of {contentSlots}{" "}
                {contentSlots === 1 ? "slot" : "slots"}
              </span>
            ) : null
          }
        />

        {record && !contentPlanned ? (
          <Alert variant="warning">
            This run was saved before new content was planned. Re-run{" "}
            {record.month} on the{" "}
            <Link
              href={accountToolHref(client.slug, "decision-engine")}
              className="underline"
            >
              Decision Engine
            </Link>{" "}
            to build it.
          </Alert>
        ) : null}

        {contentPlanned && contentSlots === 0 && newContent.length === 0 ? (
          <Alert variant="info">
            {emptyContent[0]?.reason ??
              `The ${record!.plan} plan includes no new pages.`}
          </Alert>
        ) : null}

        {contentPlanned ? renderPool(newContent, emptyContent, "content-slot") : null}

        {contentPlanned && scan && !scan.blocked && (scan.tracked ?? 0) > 0 ? (
          <p className="mt-3 text-xs text-[var(--text-tertiary)]">
            Checked {scan.tracked} tracked terms against {scan.pages_searched} crawled
            pages: {scan.mapped ?? 0} mapped to a page, {scan.covered ?? 0} already
            covered by one, {scan.ranking ?? 0} already ranking, {scan.brand ?? 0} brand
            queries, {scan.no_metrics ?? 0} without volume and difficulty,{" "}
            {scan.small ?? 0} under the volume floor.
          </p>
        ) : null}

        {contentPlanned && scan && !scan.blocked && (scan.demand_queries ?? 0) > 0 ? (
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
            Beyond tracked terms: Search Console showed {scan.demand_queries} queries in
            the last 90 days. {scan.demand_small ?? 0} drew too few impressions,{" "}
            {scan.demand_tracked ?? 0} are already tracked or mapped,{" "}
            {scan.demand_brand ?? 0} are brand queries, {scan.demand_earning ?? 0} already
            earn a top-10 position and {scan.demand_covered ?? 0} have a page about them.
            That leaves {scan.demand_gaps ?? 0} with a price and{" "}
            {scan.demand_unpriced ?? 0} waiting for one.
          </p>
        ) : null}

        {contentPlanned && scan && !scan.blocked && (scan.competitor_keywords ?? 0) > 0 ? (
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
            Competitors: the closest ones rank in the top ten for {scan.competitor_keywords}{" "}
            terms. {scan.competitor_tracked ?? 0} are already tracked or mapped,{" "}
            {scan.competitor_brand ?? 0} name a brand, {scan.competitor_small ?? 0} are too
            small to chase, {scan.competitor_earning ?? 0} already earn a top-10 position
            here and {scan.competitor_covered ?? 0} have a page about them. That leaves{" "}
            {scan.competitor_gaps ?? 0} with no page on this site.
          </p>
        ) : null}
      </section>

      {contentAlsoFound.length > 0 ? (
        <section className="workspace-section">
          <SectionHeader
            title="Also missing a page"
            description="Terms the engine found no page for and the plan had no room for."
            actions={
              <span className="text-xs text-[var(--text-tertiary)]">
                {contentAlsoFound.length} more
              </span>
            }
          />
          <CandidateTable rows={contentAlsoFound} kind="term" />
        </section>
      ) : null}

        </>
      ) : null}

      {alsoFound.length > 0 ? (
        <section className="workspace-section">
          <SectionHeader
            title="Also losing ground"
            description="Pages the engine ranked and the plan had no room for. Not padding the plan with them is the point; seeing them is how you argue with it."
            actions={
              <span className="text-xs text-[var(--text-tertiary)]">
                {alsoFound.length} more
              </span>
            }
          />
          <CandidateTable rows={alsoFound} kind="page" />
        </section>
      ) : null}

      {retainerResults.length > 0 ? (
        <section className="workspace-section">
          <SectionHeader
            title="Last month's results"
            description="Each refresh and new page is checked on the metric it was meant to move."
          />
          <PreviousResults rows={retainerResults} empty="" />
        </section>
      ) : null}

    </section>
  );
}
