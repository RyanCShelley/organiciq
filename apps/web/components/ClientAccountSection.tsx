import { ClientSettingsForm } from "@/components/ClientSettingsForm";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch, type Client, type Tier } from "@/lib/api";
import type { SettingsSection } from "@/lib/client-settings";

export async function ClientAccountSection({ client, section = "general", continueHref }: { client: Client; section?: SettingsSection; continueHref?: string }) {
  const [record, tiers, me] = await Promise.allSettled([
    apiFetch<Client>(`/clients/${client.id}`, { clientId: client.id }),
    apiFetch<Tier[]>("/admin/tiers"),
    apiFetch<{ role: string }>("/auth/me", { clientId: client.id }),
  ]);
  const title = { general: "General Information", connections: "Teamwork destination", goals: "Monthly lead goals", competitors: "Competitors", advanced: "Advanced Settings" }[section];
  if (record.status === "rejected") return <Alert variant="danger">Client settings could not be loaded. Reload before editing to avoid overwriting saved values.</Alert>;
  return <section className="workspace-section"><SectionHeader title={title} description={section === "general" ? "The essentials for this client." : undefined} /><div className="workspace-panel">
    <ClientSettingsForm key={`${client.id}-${section}`} client={record.value} tiers={tiers.status === "fulfilled" ? tiers.value : []} canEditPlan={me.status === "fulfilled" && me.value.role === "sma_admin" && tiers.status === "fulfilled" && tiers.value.some(t => t.id === record.value.tier_id)} section={section} continueHref={continueHref} />
  </div></section>;
}
