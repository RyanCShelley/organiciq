import Link from "next/link";

import { PlatformNav } from "@/components/PlatformNav";
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
      <h1 className="text-2xl font-semibold">Platform</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Cross-client operations: integration status, sync health, and jobs. Open a client workspace
        to connect OAuth, map properties, and configure conversions.
      </p>

      {error ? (
        <p className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          {error}
        </p>
      ) : null}

      <div className="mt-6 overflow-x-auto rounded-xl border border-[var(--border)]">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-white/5 text-[var(--muted)]">
            <tr>
              <th className="px-4 py-3 font-medium">Client</th>
              <th className="px-4 py-3 font-medium">GSC</th>
              <th className="px-4 py-3 font-medium">GA4</th>
              <th className="px-4 py-3 font-medium">SE Ranking</th>
              <th className="px-4 py-3 font-medium">Data sources</th>
              <th className="px-4 py-3 font-medium">Workspace</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.client_id} className="border-t border-[var(--border)]">
                <td className="px-4 py-3">
                  <div className="font-medium">{row.client_name}</div>
                  <div className="text-[var(--muted)]">{row.domain}</div>
                </td>
                <td className="px-4 py-3">{row.integrations.gsc}</td>
                <td className="px-4 py-3">{row.integrations.ga4}</td>
                <td className="px-4 py-3">{row.integrations.se_ranking}</td>
                <td className="px-4 py-3">
                  {row.sources_healthy}/{row.sources_total} healthy
                </td>
                <td className="px-4 py-3">
                  <Link
                    href={`/clients/${row.client_id}`}
                    className="text-[var(--accent)] hover:underline"
                  >
                    Open workspace
                  </Link>
                </td>
              </tr>
            ))}
            {rows.length === 0 && !error ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-[var(--muted)]">
                  No clients yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
