import Link from "next/link";

import { PlatformNav } from "@/components/PlatformNav";
import { DataTable } from "@/components/analytics/DataTable";
import { Alert } from "@/components/ui/Alert";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch, type PlatformOverviewRow } from "@/lib/api";

export default async function PlatformOverviewPage() {
  let rows: PlatformOverviewRow[] = [];
  let error: string | null = null;

  try {
    rows = await apiFetch<PlatformOverviewRow[]>("/admin/platform/overview");
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load platform overview";
  }

  return (
    <section>
      <PlatformNav active="/platform" />
      <PageHeader
        title="Platform"
        description="Cross-client operations: integration status, sync health, and jobs. Open a client workspace to connect OAuth, map properties, and configure conversions."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <section className="mt-4 workspace-section">
        <SectionHeader
          title="Clients"
          description="Integration connection state and source health at a glance."
        />
        <div className="workspace-panel">
          <DataTable
            columns={[
              {
                key: "client",
                header: "Client",
                render: (row) => (
                  <div>
                    <div className="font-medium">{row.client_name}</div>
                    <div className="text-xs text-[var(--text-tertiary)]">{row.domain}</div>
                  </div>
                ),
              },
              { key: "gsc", header: "GSC", render: (row) => row.integrations.gsc },
              { key: "ga4", header: "GA4", render: (row) => row.integrations.ga4 },
              {
                key: "ser",
                header: "SE Ranking",
                render: (row) => row.integrations.se_ranking,
              },
              {
                key: "health",
                header: "Data sources",
                render: (row) => `${row.sources_healthy}/${row.sources_total} healthy`,
              },
              {
                key: "workspace",
                header: "Workspace",
                render: (row) => (
                  <Link
                    href={`/clients/${row.client_id}`}
                    className="text-[var(--brand-teal-hover)] underline"
                  >
                    Open workspace
                  </Link>
                ),
              },
            ]}
            rows={rows}
            getRowKey={(row) => row.client_id}
            emptyMessage="No clients yet."
          />
        </div>
      </section>
    </section>
  );
}
