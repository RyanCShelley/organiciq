import { ClientWorkspaceNav } from "@/components/ClientWorkspaceNav";
import { EnqueueJobForm } from "@/components/EnqueueJobForm";
import { apiFetch, type SyncJob } from "@/lib/api";
import { clientHref } from "@/lib/client-path";
import { requireWorkspaceClient } from "@/lib/context";

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
      <h1 className="text-2xl font-semibold">Sync Jobs</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Enqueue ingestion for {client.client_name}. All clients are visible on Platform → Sync Jobs.
      </p>

      <div className="mt-4">
        <EnqueueJobForm clientId={clientId} />
      </div>

      {error ? (
        <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
          {error}
        </p>
      ) : null}

      <div className="mt-6 overflow-x-auto rounded-xl border border-[var(--border)]">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-white/5 text-[var(--muted)]">
            <tr>
              <th className="px-4 py-3 font-medium">Source</th>
              <th className="px-4 py-3 font-medium">Window</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Error</th>
              <th className="px-4 py-3 font-medium">Created</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-[var(--border)]">
                <td className="px-4 py-3">{row.source}</td>
                <td className="px-4 py-3 text-[var(--muted)]">
                  {row.start_date} → {row.end_date}
                </td>
                <td className="px-4 py-3">{row.status}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{row.error_message ?? "—"}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{row.created_at}</td>
              </tr>
            ))}
            {rows.length === 0 && !error ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-[var(--muted)]">
                  No jobs yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
