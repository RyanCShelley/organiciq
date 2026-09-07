import Link from "next/link";

import { PlatformNav } from "@/components/PlatformNav";
import { DataTable } from "@/components/analytics/DataTable";
import { StatusBadge } from "@/components/analytics/StatusBadge";
import { Alert } from "@/components/ui/Alert";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch, type PlatformDataHealthRow } from "@/lib/api";

export default async function PlatformDataHealthPage() {
  let rows: PlatformDataHealthRow[] = [];
  let error: string | null = null;

  try {
    rows = await apiFetch<PlatformDataHealthRow[]>("/admin/platform/data-health");
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load data health";
  }

  return (
    <section>
      <PlatformNav active="/platform/data-health" />
      <PageHeader
        title="Data Health"
        description="Freshness and validation for every client and source. Never treat stale data as current."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <section className="mt-4 workspace-section">
        <SectionHeader title="Sources" description="Per-client watermark and validation status." />
        <div className="workspace-panel">
          <DataTable
            columns={[
              {
                key: "client",
                header: "Client",
                render: (row) => (
                  <Link
                    href={`/clients/${row.client_id}`}
                    className="text-[var(--brand-teal-hover)] underline"
                  >
                    {row.client_name}
                  </Link>
                ),
              },
              { key: "source", header: "Source", render: (row) => row.source },
              {
                key: "status",
                header: "Status",
                render: (row) => (
                  <StatusBadge
                    available={row.status === "Healthy"}
                    availableLabel={row.status}
                    unavailableLabel={row.status}
                  />
                ),
              },
              {
                key: "fact",
                header: "Fact Through",
                render: (row) => row.fact_through ?? "—",
              },
              {
                key: "sync",
                header: "Last Sync",
                render: (row) => row.last_sync ?? "—",
              },
              {
                key: "validation",
                header: "Validation",
                render: (row) => row.validation ?? "—",
              },
            ]}
            rows={rows}
            getRowKey={(row) => `${row.client_id}-${row.source}`}
            emptyMessage="No data health rows yet."
          />
        </div>
      </section>
    </section>
  );
}
