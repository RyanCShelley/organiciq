import Link from "next/link";

import { PlatformNav } from "@/components/PlatformNav";
import { DataTable } from "@/components/analytics/DataTable";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch, type PlatformJobRow } from "@/lib/api";
import { jobBadgeVariant, jobStatusLabel } from "@/lib/jobs";

export default async function PlatformJobsPage() {
  let rows: PlatformJobRow[] = [];
  let error: string | null = null;

  try {
    rows = await apiFetch<PlatformJobRow[]>("/admin/platform/jobs");
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load sync jobs";
  }

  return (
    <section>
      <PlatformNav active="/platform/jobs" />

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <section className="workspace-section">
        <SectionHeader title="Recent jobs" description="Newest jobs across the platform." />
        <div className="workspace-panel">
          <DataTable
            columns={[
              {
                key: "client",
                header: "Client",
                render: (row) => (
                  <Link
                    href={`/clients/${row.client_slug}/jobs`}
                    className="text-[var(--brand-teal-hover)] underline"
                  >
                    {row.client_name}
                  </Link>
                ),
              },
              { key: "source", header: "Source", render: (row) => row.source },
              {
                key: "window",
                header: "Window",
                render: (row) => `${row.start_date} → ${row.end_date}`,
              },
              {
                key: "status",
                header: "Status",
                render: (row) => (
                  <Badge variant={jobBadgeVariant(row.status)}>
                    {jobStatusLabel(row.status)}
                  </Badge>
                ),
              },
              {
                key: "error",
                header: "Error",
                render: (row) => row.error_message ?? "—",
              },
              {
                key: "created",
                header: "Created",
                render: (row) => row.created_at ?? "—",
              },
            ]}
            rows={rows}
            getRowKey={(row) => row.id}
            emptyMessage="No jobs yet."
          />
        </div>
      </section>
    </section>
  );
}
