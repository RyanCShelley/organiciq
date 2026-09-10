import Link from "next/link";

import { DeleteClientButton } from "@/components/DeleteClientButton";
import { DataTable } from "@/components/analytics/DataTable";
import { StatusBadge } from "@/components/analytics/StatusBadge";
import { Alert } from "@/components/ui/Alert";
import { apiFetch, type Client, type PlatformOverviewRow } from "@/lib/api";

type ClientRow = Client & { overview?: PlatformOverviewRow };

export default async function ClientsIndexPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const oauth = typeof params.oauth === "string" ? params.oauth : null;
  const oauthMessage = typeof params.message === "string" ? params.message : null;

  let clients: Client[] = [];
  let overview: PlatformOverviewRow[] = [];
  let error: string | null = null;

  try {
    clients = await apiFetch<Client[]>("/clients");
  } catch (e) {
    const message = e instanceof Error ? e.message : "Failed to load clients";
    error = message.toLowerCase().includes("invalid or expired token")
      ? "Your API session expired. Refresh the page or sign in again."
      : message;
  }

  // Source health is a nice-to-have column — never fail the list over it.
  try {
    overview = await apiFetch<PlatformOverviewRow[]>("/admin/platform/overview");
  } catch {
    overview = [];
  }

  const overviewById = new Map(overview.map((row) => [row.client_id, row]));
  const rows: ClientRow[] = clients.map((client) => ({
    ...client,
    overview: overviewById.get(client.id),
  }));

  return (
    <section>
      {oauth === "error" ? (
        <Alert variant="danger" className="mb-4">
          OAuth failed{oauthMessage ? `: ${oauthMessage}` : ""}
        </Alert>
      ) : null}

      {error ? (
        <Alert variant="danger" className="mb-4">
          {error}
        </Alert>
      ) : null}

      <DataTable
        columns={[
          {
            key: "client",
            header: "Client",
            render: (row) => (
              <Link
                href={`/clients/${row.slug}`}
                className="block min-w-0 transition-colors hover:text-[var(--brand-teal-hover)]"
              >
                <span className="block font-semibold">{row.client_name}</span>
                <span className="block font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]">
                  {row.domain}
                </span>
              </Link>
            ),
          },
          {
            key: "lead_goal",
            header: "Monthly lead goal",
            align: "right",
            render: (row) =>
              row.monthly_lead_goal != null ? row.monthly_lead_goal.toLocaleString() : "—",
          },
          {
            key: "status",
            header: "Status",
            render: (row) => (
              <StatusBadge
                available={row.status === "active"}
                availableLabel={row.status}
                unavailableLabel={row.status}
              />
            ),
          },
          {
            key: "health",
            header: "Data health",
            render: (row) =>
              row.overview ? (
                <StatusBadge
                  available={row.overview.sources_healthy === row.overview.sources_total}
                  availableLabel={`${row.overview.sources_healthy}/${row.overview.sources_total} healthy`}
                  unavailableLabel={`${row.overview.sources_healthy}/${row.overview.sources_total} healthy`}
                />
              ) : (
                <span className="text-[var(--text-tertiary)]">—</span>
              ),
          },
          {
            key: "actions",
            header: "",
            align: "right",
            render: (row) => (
              <span className="inline-flex items-center gap-2">
                <Link href={`/clients/${row.slug}`} className="btn btn-secondary btn-sm">
                  Open workspace
                </Link>
                <DeleteClientButton clientId={row.id} clientName={row.client_name} />
              </span>
            ),
          },
        ]}
        rows={rows}
        getRowKey={(row) => row.id}
        emptyMessage="No clients yet."
      />
    </section>
  );
}
