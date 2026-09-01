import Link from "next/link";

import { PlatformNav } from "@/components/PlatformNav";
import { apiFetch, type PlatformJobRow } from "@/lib/api";

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
      <h1 className="text-2xl font-semibold">Sync Jobs</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Recent ingestion jobs across all clients. Enqueue new jobs from a client workspace.
      </p>

      {error ? (
        <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
          {error}
        </p>
      ) : null}

      <div className="mt-6 overflow-x-auto rounded-xl border border-[var(--border)]">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-white/5 text-[var(--muted)]">
            <tr>
              <th className="px-4 py-3 font-medium">Client</th>
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
                <td className="px-4 py-3">
                  <Link href={`/clients/${row.client_id}/jobs`} className="hover:underline">
                    {row.client_name}
                  </Link>
                </td>
                <td className="px-4 py-3">{row.source}</td>
                <td className="px-4 py-3 text-[var(--muted)]">
                  {row.start_date} → {row.end_date}
                </td>
                <td className="px-4 py-3">{row.status}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{row.error_message ?? "—"}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{row.created_at ?? "—"}</td>
              </tr>
            ))}
            {rows.length === 0 && !error ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-[var(--muted)]">
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
