import Link from "next/link";

import { SearchOpportunitiesTable } from "@/components/DecisionEngine/SearchOpportunitiesTable";
import { SlotActionBar } from "@/components/DecisionEngine/SlotActionBar";
import { EmptySlotCard, SlotCard } from "@/components/DecisionEngine/SlotCard";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch } from "@/lib/api";
import { accountToolHref } from "@/lib/account-routes";
import { requireAccountClient } from "@/lib/account-routes.server";
import { resolveDateRange } from "@/lib/context";
import {
  normalizeDiagnoseResponse,
  type DiagnoseResponse,
  type SearchOpportunity,
} from "@/lib/decision-engine";
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
 * losing ground. Two allowances, two pools, one machine — the cards,
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
  const { from, to } = await resolveDateRange(query);

  let record: MonthlyRecord | null = null;
  let recordError: string | null = null;
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
        apiFetch<Assignee[]>("/decisions/assignees", { clientId }),
      ]);
      slotStates = new Map(workflow.actions.map((row) => [row.uid, row]));
      teamworkReady = workflow.teamwork_ready;
      assignees = people;
    } catch {
      // Leave the plan readable.
    }
  }

  let contentOpps: SearchOpportunity[] = [];
  try {
    const diagnose = normalizeDiagnoseResponse(
      await apiFetch<DiagnoseResponse>(
        `/decisions/diagnose?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        { clientId },
      ),
    );
    contentOpps = diagnose.search_opportunities ?? [];
  } catch {
    // The striking-distance list is a secondary read. Losing it must not
    // take the plan down with it.
  }

  const updates = record?.updates ?? [];
  const emptyUpdates = record?.empty_update_slots ?? [];
  const slots = record?.update_slots ?? 0;
  // Everything the engine weighed and could not fit. The bulk of what it
  // found lives here, and a plan you cannot argue with is not a plan.
  const alsoFound = (record?.update_candidates ?? []).filter(
    (row) => row.slot === null,
  );

  return (
    <section>
      {recordError ? <Alert variant="danger">{recordError}</Alert> : null}

      <section className="workspace-section">
        <SectionHeader
          title="Content refresh"
          description="Pages losing ground, ranked by the impressions they used to draw and no longer do. This is retainer work — it is inside the monthly fee, which is why it has its own allowance and does not compete with growth actions."
          actions={
            record ? (
              <span className="text-xs text-[var(--text-tertiary)]">
                {record.month} · {updates.length} of {slots}{" "}
                {slots === 1 ? "slot" : "slots"}
              </span>
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

        {record && slots === 0 && updates.length === 0 ? (
          <Alert variant="info">
            {emptyUpdates[0]?.reason ??
              `The ${record.plan} plan includes no content refreshes.`}
          </Alert>
        ) : null}

        <div className="space-y-3">
          {updates.map((action) => (
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
                slug={client.slug}
                month={record!.month}
                teamworkReady={teamworkReady}
              />
            </SlotCard>
          ))}
          {emptyUpdates.map((slot) => (
            <EmptySlotCard key={slot.slot} slot={slot.slot} reason={slot.reason} />
          ))}
        </div>
      </section>

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
          <div className="table-shell overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th>Page</th>
                  <th>What it needs</th>
                  <th className="text-right">Impressions lost</th>
                </tr>
              </thead>
              <tbody>
                {alsoFound.slice(0, 25).map((row) => (
                  <tr key={row.action_uid}>
                    <td className="font-[family-name:var(--font-mono)] text-[12.5px]">
                      {row.target_url.replace(/^https?:\/\/[^/]+/, "") || "/"}
                    </td>
                    <td className="text-[13px]">{row.title}</td>
                    <td className="whitespace-nowrap text-right tabular-nums">
                      {Math.round(row.score).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {contentOpps.length > 0 ? (
        <SearchOpportunitiesTable
          items={contentOpps}
          title="Close to page one"
          description="Pages averaging positions 8 to 20 with real demand — not decay, but the shortest distance to a result. Ranked by impressions."
        />
      ) : null}
    </section>
  );
}
