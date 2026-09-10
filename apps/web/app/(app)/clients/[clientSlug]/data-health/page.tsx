import { ClientWorkspaceNav } from "@/components/ClientWorkspaceNav";
import { DataTable } from "@/components/analytics/DataTable";
import { StatusBadge } from "@/components/analytics/StatusBadge";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch, type DataHealthRow } from "@/lib/api";
import { clientHref } from "@/lib/client-path";
import { requireWorkspaceClient } from "@/lib/context";

export default async function ClientDataHealthPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = await requireWorkspaceClient(clientSlug, "data-health");
  const clientId = client.id;

  let rows: DataHealthRow[] = [];
  let error: string | null = null;

  try {
    rows = await apiFetch<DataHealthRow[]>("/admin/data-health", { clientId });
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load data health";
  }

  const healthy = rows.filter((row) => row.status === "Healthy").length;

  return (
    <section>
      <ClientWorkspaceNav clientSlug={client.slug} active={clientHref(client.slug, "data-health")} />

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <section className="workspace-section">
        <SectionHeader
          title="Sources"
          description={`Freshness and validation for ${client.client_name}. Cross-client view is on Platform → Data health.`}
          actions={
            rows.length > 0 ? (
              <span className="text-xs text-[var(--text-tertiary)]">
                {healthy}/{rows.length} sources healthy
              </span>
            ) : null
          }
        />
        <DataTable
          columns={[
            {
              key: "source",
              header: "Source",
              render: (row) => (
                <span className="font-medium">{row.source.replaceAll("_", " ")}</span>
              ),
            },
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
              key: "fact_through",
              header: "Fact through",
              render: (row) => (
                <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--text-secondary)]">
                  {row.fact_through ?? "—"}
                </span>
              ),
            },
            {
              key: "last_sync",
              header: "Last sync",
              render: (row) => (
                <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--text-secondary)]">
                  {row.last_sync ?? "—"}
                </span>
              ),
            },
            {
              key: "validation",
              header: "Validation",
              render: (row) => (
                <span className="text-[var(--text-secondary)]">{row.validation ?? "—"}</span>
              ),
            },
          ]}
          rows={rows}
          getRowKey={(row) => row.source}
          emptyMessage="No watermark data yet."
        />
      </section>
    </section>
  );
}
