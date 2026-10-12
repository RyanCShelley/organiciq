import Link from "next/link";

import { ClientSettingsForm } from "@/components/ClientSettingsForm";
import { ClientWorkspaceNav } from "@/components/ClientWorkspaceNav";
import { ClientTeamPanel } from "@/components/ClientTeamPanel";
import {
  ExcludedPagesPanel,
  type ExcludedPage,
} from "@/components/ExcludedPagesPanel";
import {
  SetupChecklist,
  type SetupState,
} from "@/components/SetupChecklist";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import {
  apiFetch,
  type Client,
  type ConversionDefinition,
  type Tier,
  type User,
} from "@/lib/api";
import type { ClientTeamMember } from "@/app/(app)/team-actions";
import { clientHref } from "@/lib/client-path";
import { requireWorkspaceClient } from "@/lib/context";

export default async function ClientSettingsPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = await requireWorkspaceClient(clientSlug);
  const clientId = client.id;

  let tiers: Tier[] = [];
  let conversions: ConversionDefinition[] = [];
  let team: ClientTeamMember[] = [];
  let users: User[] = [];
  // These endpoints are admin-only; a 403 means "cannot manage", not an error.
  let canManageTeam = true;
  let loadError: string | null = null;
  let setup: SetupState | null = null;
  let excluded: ExcludedPage[] = [];

  try {
    const [tierRows, conversionRows, freshClient] = await Promise.all([
      apiFetch<Tier[]>("/admin/tiers"),
      apiFetch<ConversionDefinition[]>("/admin/conversion-definitions", { clientId }),
      apiFetch<Client>(`/clients/${clientId}`, { clientId }),
    ]);
    tiers = tierRows;
    conversions = conversionRows;
    Object.assign(client, freshClient);
  } catch (e) {
    loadError = e instanceof Error ? e.message : "Failed to load client settings";
  }

  try {
    excluded = await apiFetch<ExcludedPage[]>("/decisions/excluded-pages", { clientId });
  } catch {
    excluded = [];
  }

  try {
    setup = await apiFetch<SetupState>(`/clients/${clientId}/setup`, { clientId });
  } catch {
    // The checklist is a guide, not the page. Losing it costs nothing else.
    setup = null;
  }

  try {
    [team, users] = await Promise.all([
      apiFetch<ClientTeamMember[]>(`/admin/clients/${clientId}/team`, { clientId }),
      apiFetch<User[]>("/admin/users", { clientId }),
    ]);
  } catch {
    canManageTeam = false;
  }

  const hasLeadConversions = conversions.some(
    (row) => row.active && row.conversion_type === "lead",
  );

  return (
    <section>
      <ClientWorkspaceNav clientSlug={client.slug} active={clientHref(client.slug)} />

      {loadError ? <Alert variant="danger">{loadError}</Alert> : null}

      <div className="space-y-[var(--section-gap)]">
        {/* First, because it is the only thing on this page that says what to
            do rather than offering another field to fill in. */}
        {setup ? (
          <section className="workspace-section">
            <SectionHeader
              title="Setup"
              description="In order, because each step reads what the one before it produced. Measured now, not remembered."
            />
            <div className="workspace-panel">
              <SetupChecklist state={setup} clientSlug={client.slug} />
            </div>
          </section>
        ) : null}

        <section className="workspace-section">
          <SectionHeader title="Account record" description="Core fields for this Organic IQ client." />
          <div className="workspace-panel">
            <ClientSettingsForm
              client={client}
              tiers={tiers}
              hasLeadConversions={hasLeadConversions}
            />
          </div>
        </section>

        <section className="workspace-section">
          <SectionHeader
            title="Pages the engine leaves alone"
            description="Sections you are not working on. The engine will not prescribe growth actions for these, and the reason stays on the record so a decision taken in March is legible in September."
          />
          <div className="workspace-panel">
            <ExcludedPagesPanel clientId={clientId} initial={excluded} />
          </div>
        </section>

        <section className="workspace-section">
          <SectionHeader
            title="Team access"
            description="Who can see this client. Team members see nothing until they are added here; admins see every client."
          />
          <div className="workspace-panel">
            <ClientTeamPanel
              clientId={clientId}
              clientName={client.client_name}
              team={team}
              users={users}
              canManage={canManageTeam}
            />
          </div>
        </section>

      </div>
    </section>
  );
}
