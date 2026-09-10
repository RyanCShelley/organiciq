import { ClientWorkspaceNav } from "@/components/ClientWorkspaceNav";
import { EnqueueJobForm } from "@/components/EnqueueJobForm";
import { DataTable } from "@/components/analytics/DataTable";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch, type SyncJob } from "@/lib/api";
import { clientHref } from "@/lib/client-path";
import { requireWorkspaceClient } from "@/lib/context";
import { jobBadgeVariant, jobStatusLabel } from "@/lib/jobs";

export default async function ClientJobsPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = await requireWorkspaceClient(clientSlug, "jobs");
  const clientId = client.id;

  let rows: SyncJob[] = [];
  let error: string | null = null;

  try {
    rows = await apiFetch<SyncJob[]>("/jobs", { clientId });
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load jobs";
  }

  return (
    <section>
      <ClientWorkspaceNav clientSlug={client.slug} active={clientHref(client.slug, "jobs")} />

      <section className="workspace-section">
        <SectionHeader
          title="Enqueue a sync"
          description={`Queue ingestion for ${client.client_name}. All clients are visible on Platform → Sync jobs.`}
        />
        <div className="workspace-panel">
          <EnqueueJobForm clientId={clientId} />
        </div>
      </section>

      {error ? (
        <Alert variant="danger" className="mt-4">
          {error}
        </Alert>
      ) : null}

      <section className="workspace-section">
        <SectionHeader title="Recent jobs" description="Newest ingestion runs for this client." />
        <DataTable
          columns={[
            {
              key: "source",
              header: "Source",
              render: (row) => <span className="font-medium">{row.source}</span>,
            },
            {
              key: "window",
              header: "Window",
              render: (row) => (
                <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--text-secondary)]">
                  {row.start_date} → {row.end_date}
                </span>
              ),
            },
            {
              key: "status",
              header: "Status",
              render: (row) => (
                <Badge variant={jobBadgeVariant(row.status)}>{jobStatusLabel(row.status)}</Badge>
              ),
            },
            {
              key: "error",
              header: "Error",
              render: (row) =>
                row.error_message ? (
                  <span className="text-[var(--danger)]">{row.error_message}</span>
                ) : (
                  <span className="text-[var(--text-tertiary)]">—</span>
                ),
            },
            {
              key: "created",
              header: "Created",
              render: (row) => (
                <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--text-secondary)]">
                  {row.created_at}
                </span>
              ),
            },
          ]}
          rows={rows}
          getRowKey={(row) => row.id}
          emptyMessage="No jobs yet."
        />
      </section>
    </section>
  );
}
