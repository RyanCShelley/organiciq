import { PlatformNav } from "@/components/PlatformNav";
import { DataTable } from "@/components/analytics/DataTable";
import { Alert } from "@/components/ui/Alert";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
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
      <PageHeader
        title="Platform Settings"
        description="Global tiers and channel rules. Client-specific conversion definitions live in each client workspace."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="mt-4 space-y-[var(--section-gap)]">
        <section className="workspace-section">
          <SectionHeader
            title="Tiers"
            description="Watchlist limits are keywords + AI prompts. New content and content refresh are per quarter; Growth Actions are per month."
          />
          <div className="workspace-panel">
            <DataTable
              columns={[
                { key: "tier", header: "Tier", render: (row) => row.tier_name },
                {
                  key: "watchlist",
                  header: "Watchlist",
                  render: (row) =>
                    row.isEnterprise
                      ? "Custom per agreement"
                      : `${row.tracked_keyword_limit} keywords + AI`,
                },
                {
                  key: "cadence",
                  header: "Cadence",
                  render: (row) =>
                    row.isEnterprise
                      ? "Custom"
                      : (row.watchlist_cadence ?? "monthly").replaceAll("_", "-"),
                },
                {
                  key: "content",
                  header: "New content /q",
                  align: "right",
                  render: (row) => (row.isEnterprise ? "Custom" : String(row.content_allowance)),
                },
                {
                  key: "refresh",
                  header: "Content refresh /q",
                  align: "right",
                  render: (row) => (row.isEnterprise ? "Custom" : String(row.update_allowance)),
                },
                {
                  key: "growth",
                  header: "Growth Actions /mo",
                  align: "right",
                  render: (row) =>
                    row.isEnterprise
                      ? "Custom"
                      : String(row.growth_action_allowance ?? "—"),
                },
              ]}
              rows={tiers.map((tier) => ({
                ...tier,
                isEnterprise:
                  tier.tier_name === "Enterprise" || tier.reporting_level === "enterprise",
              }))}
              getRowKey={(row) => row.id}
              emptyMessage="No tiers configured."
            />
          </div>
        </section>

        <section className="workspace-section">
          <SectionHeader
            title="Channel rules"
            description="How GA4 source/medium (and host) map into Organic IQ channels."
          />
          <div className="workspace-panel">
            <DataTable
              columns={[
                { key: "channel", header: "Channel", render: (row) => row.channel },
                {
                  key: "source",
                  header: "Source",
                  render: (row) => row.match_source ?? "—",
                },
                {
                  key: "medium",
                  header: "Medium",
                  render: (row) => row.match_medium ?? "—",
                },
                {
                  key: "host",
                  header: "Host contains",
                  render: (row) => row.match_host_contains ?? "—",
                },
                {
                  key: "priority",
                  header: "Priority",
                  align: "right",
                  render: (row) => String(row.priority),
                },
              ]}
              rows={rules}
              getRowKey={(row) => row.id}
              emptyMessage="No channel rules configured."
            />
          </div>
        </section>
      </div>
    </section>
  );
}
