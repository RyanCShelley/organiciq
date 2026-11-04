import {
  AnnotationCreateForm,
  AnnotationImportPanel,
} from "@/components/Annotations/AnnotationForms";
import { WorkHub, type WorkItem } from "@/components/Annotations/WorkHub";
import { Alert } from "@/components/ui/Alert";
import { apiFetch } from "@/lib/api";
import { requireAccountClient } from "@/lib/account-routes.server";
import type { AnnotationRow } from "@/lib/annotations";
import type {
  MonthlyRecord,
  RunSummary,
  Workflow,
  Assignee,
} from "@/lib/monthly-record";
import { resolveDateRange } from "@/lib/context";
export default async function WorkPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const client = await requireAccountClient(
    (await params).clientSlug,
    "annotations",
  );
  const { from, to } = await resolveDateRange(await searchParams);
  const context = new URLSearchParams({ from, to, range: "custom" });
  let rows: AnnotationRow[] = [],
    assignees: Assignee[] = [],
    items: WorkItem[] = [];
  const failures: string[] = [];
  let failure: string | null = null;
  try {
    const [loadedRows, runs, loadedAssignees] = await Promise.all([
      apiFetch<AnnotationRow[]>("/annotations", { clientId: client.id }),
      apiFetch<RunSummary[]>("/decisions/records", { clientId: client.id }),
      apiFetch<Assignee[]>("/decisions/assignees", {
        clientId: client.id,
      }).catch(() => []),
    ]);
    rows = loadedRows;
    assignees = loadedAssignees;
    const months = await Promise.all(
      runs.map(async (run) => {
        try {
          const record = await apiFetch<MonthlyRecord>(
            `/decisions/records/${run.month}`,
            { clientId: client.id },
          );
          const workflow = await apiFetch<Workflow>(
            `/decisions/records/${run.month}/workflow`,
            { clientId: client.id },
          );
          const states = new Map(workflow.actions.map((row) => [row.uid, row]));
          const approved = Boolean(record.plan_review?.approved_at);
          return record.actions
            .filter((action) => {
              const state = states.get(action.action_uid);
              return (
                approved ||
                Boolean(
                  state?.assignee_email || state?.sent_at || state?.shipped_on,
                )
              );
            })
            .map((action) => ({
              month: run.month,
              action,
              state: states.get(action.action_uid),
              teamworkReady: workflow.teamwork_ready,
              approved,
            }));
        } catch {
          failures.push(run.month);
          return [];
        }
      }),
    );
    items = months.flat() as WorkItem[];
  } catch (error) {
    failure = error instanceof Error ? error.message : "Work could not load";
  }
  if (failure) return <Alert variant="danger">{failure}</Alert>;
  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-xl font-bold">Work & Results</h2>
        <p className="text-sm text-[var(--text-secondary)]">
          Assign approved work, deliver it, record completion and review
          results.
        </p>
      </div>
      {failures.length > 0 && (
        <Alert variant="warning">
          Work could not load for {failures.join(", ")}. Reload before making
          delivery decisions.
        </Alert>
      )}
      <WorkHub
        items={items}
        rows={rows}
        assignees={assignees}
        clientId={client.id}
        slug={client.slug}
        engineHref={`/${client.slug}/decision-engine?${context}`}
      />
      <details className="workspace-section">
        <summary className="cursor-pointer font-semibold">
          Log completed work
        </summary>
        <div className="workspace-panel">
          <AnnotationCreateForm clientId={client.id} />
        </div>
      </details>
      <details className="workspace-section">
        <summary className="cursor-pointer font-semibold">
          Import past completed work
        </summary>
        <div className="workspace-panel">
          <AnnotationImportPanel clientId={client.id} />
        </div>
      </details>
    </section>
  );
}
