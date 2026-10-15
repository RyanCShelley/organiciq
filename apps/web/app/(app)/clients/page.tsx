import Link from "next/link";

import { AddClientForm } from "@/components/AddClientForm";
import { DeleteClientButton } from "@/components/DeleteClientButton";
import {
  PortfolioOverview,
  type Portfolio,
} from "@/components/PortfolioOverview";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { DataTable } from "@/components/analytics/DataTable";
import { StatusBadge } from "@/components/analytics/StatusBadge";
import { Alert } from "@/components/ui/Alert";
import { getClients } from "@/lib/clients";
import { apiFetch, type Client, type PlatformOverviewRow, type Tier } from "@/lib/api";
import { tableControls, filterRows } from "@/lib/table-sort";

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
  let tiers: Tier[] = [];
  let portfolio: Portfolio | null = null;
  let error: string | null = null;

  // Four independent calls, made together. They were awaited one after another,
  // so the page waited for the sum. Each keeps its own failure rule: only the
  // client list is allowed to fail the page.
  const [clientsResult, overviewResult, tiersResult, portfolioResult] = await Promise.allSettled([
    getClients(),
    // Source health is a nice-to-have column — never fail the list over it.
    apiFetch<PlatformOverviewRow[]>("/admin/platform/overview"),
    // Tiers populate the Add client form; its own empty state covers a failure.
    apiFetch<Tier[]>("/admin/tiers"),
    // Its own call, so a failure costs the overview and not the client list.
    apiFetch<Portfolio>("/decisions/portfolio"),
  ]);

  if (clientsResult.status === "fulfilled") {
    clients = clientsResult.value;
  } else {
    const e = clientsResult.reason;
    const message = e instanceof Error ? e.message : "Failed to load clients";
    error = message.toLowerCase().includes("invalid or expired token")
      ? "Your API session expired. Refresh the page or sign in again."
      : message;
  }
  overview = overviewResult.status === "fulfilled" ? overviewResult.value : [];
  tiers = tiersResult.status === "fulfilled" ? tiersResult.value : [];
  portfolio = portfolioResult.status === "fulfilled" ? portfolioResult.value : null;

  const clientsTable = tableControls(params, "/clients", "c");
  const overviewById = new Map(overview.map((row) => [row.client_id, row]));
  const rows: ClientRow[] = clients.map((client) => ({
    ...client,
    overview: overviewById.get(client.id),
  }));

  return (
    <section>
      <div className="mb-4 flex justify-end">
        <AddClientForm tiers={tiers} />
      </div>

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

      {portfolio ? (
        <section className="workspace-section mb-[var(--section-gap)]">
          <SectionHeader
            title="Portfolio"
            description="Every client's saved run, counted rather than recomputed — so a row here and the client's own page cannot disagree."
          />
          <PortfolioOverview data={portfolio} />
        </section>
      ) : null}

      <SectionHeader title="All clients" description="Every client record and its data health." />

      <DataTable
        columns={[
          {
            key: "client",
            header: "Client",
            sortValue: (row: ClientRow) => row.client_name,
            sortInitial: "asc" as const,
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
            sortValue: (row: ClientRow) => row.monthly_lead_goal,
            align: "right",
            render: (row) =>
              row.monthly_lead_goal != null ? row.monthly_lead_goal.toLocaleString() : "—",
          },
          {
            key: "status",
            header: "Status",
            sortValue: (row: ClientRow) => row.status,
            sortInitial: "asc" as const,
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
            sortValue: (row: ClientRow) => row.overview ? row.overview.sources_healthy : null,
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
        rows={filterRows(rows, clientsTable.searchValue, (row) => [
          row.client_name,
          row.domain,
        ])}
        sort={clientsTable.sort}
        sortHref={clientsTable.sortHref}
        searchAction={clientsTable.searchAction}
        searchParam={clientsTable.searchParam}
        searchValue={clientsTable.searchValue}
        searchPlaceholder="Search clients…"
        getRowKey={(row) => row.id}
        emptyMessage="No clients yet."
      />
    </section>
  );
}
