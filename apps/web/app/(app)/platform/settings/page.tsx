import { PlatformNav } from "@/components/PlatformNav";
import { apiFetch, type ChannelRule, type Tier } from "@/lib/api";

export default async function PlatformSettingsPage() {
  let tiers: Tier[] = [];
  let rules: ChannelRule[] = [];
  let error: string | null = null;

  try {
    tiers = await apiFetch<Tier[]>("/admin/tiers");
    rules = await apiFetch<ChannelRule[]>("/admin/channel-rules");
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load platform settings";
  }

  return (
    <section>
      <PlatformNav active="/platform/settings" />
      <h1 className="text-2xl font-semibold">Platform Settings</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Global tiers and channel rules. Client-specific conversion definitions live in each client
        workspace.
      </p>

      {error ? (
        <p className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          {error}
        </p>
      ) : null}

      <h2 className="mt-8 text-lg font-medium">Tiers</h2>
      <ConfigTable
        headers={["Name", "Keywords", "Prompts", "Content", "Reporting"]}
        rows={tiers.map((tier) => [
          tier.tier_name,
          String(tier.tracked_keyword_limit),
          String(tier.tracked_prompt_limit),
          String(tier.content_allowance),
          tier.reporting_level,
        ])}
      />

      <h2 className="mt-8 text-lg font-medium">Channel rules</h2>
      <ConfigTable
        headers={["Channel", "Source", "Medium", "Host contains", "Priority"]}
        rows={rules.map((rule) => [
          rule.channel,
          rule.match_source ?? "—",
          rule.match_medium ?? "—",
          rule.match_host_contains ?? "—",
          String(rule.priority),
        ])}
      />
    </section>
  );
}

function ConfigTable({
  headers,
  rows,
  empty = "No rows.",
}: {
  headers: string[];
  rows: string[][];
  empty?: string;
}) {
  return (
    <div className="mt-3 overflow-x-auto rounded-xl border border-[var(--border)]">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-white/5 text-[var(--muted)]">
          <tr>
            {headers.map((header) => (
              <th key={header} className="px-4 py-3 font-medium">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-t border-[var(--border)]">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-4 py-3">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 ? (
            <tr>
              <td colSpan={headers.length} className="px-4 py-6 text-[var(--muted)]">
                {empty}
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
