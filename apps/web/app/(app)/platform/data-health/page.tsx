import Link from "next/link";

import { PlatformNav } from "@/components/PlatformNav";
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
      <h1 className="text-2xl font-semibold">Data Health</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Freshness and validation for every client and source. Never treat stale data as current.
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
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Fact Through</th>
              <th className="px-4 py-3 font-medium">Last Sync</th>
              <th className="px-4 py-3 font-medium">Validation</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.client_id}-${row.source}`} className="border-t border-[var(--border)]">
                <td className="px-4 py-3">
                  <Link href={`/clients/${row.client_id}`} className="hover:underline">
                    {row.client_name}
                  </Link>
                </td>
                <td className="px-4 py-3">{row.source}</td>
                <td className="px-4 py-3">{row.status}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{row.fact_through ?? "—"}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{row.last_sync ?? "—"}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{row.validation ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
