import { notFound } from "next/navigation";

import { GeneralForm } from "@/components/ClientForms";
import { SetupChecklist, type SetupState } from "@/components/SetupChecklist";
import { apiFetch } from "@/lib/api";
import { getClients, getTiers } from "@/lib/clients";

export const metadata = { title: "Settings · General" };

export default async function GeneralPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const [clients, tiers] = await Promise.all([getClients(), getTiers()]);
  const client = clients.find((c) => c.slug === clientSlug);
  if (!client) notFound();

  const setup = await apiFetch<SetupState>(`/clients/${client.id}/setup`).catch(() => null);

  return (
    <div className="space-y-6">
      {setup ? (
        <SetupChecklist
          clientId={client.id}
          slug={client.slug}
          clientName={client.client_name}
          serviceMode={client.service_mode ?? "execution"}
          setup={setup}
        />
      ) : null}
      <GeneralForm client={client} tiers={tiers} />
    </div>
  );
}
