import { ClientTeamPanel } from "@/components/ClientTeamPanel";
import type { ClientTeamMember } from "@/app/(app)/team-actions";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch, type User } from "@/lib/api";
import { requireWorkspaceClient } from "@/lib/context";
export default async function TeamPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = await requireWorkspaceClient(clientSlug, "team");
  let team: ClientTeamMember[] = [], users: User[] = [], canManage = true;
  try { [team, users] = await Promise.all([apiFetch<ClientTeamMember[]>(`/admin/clients/${client.id}/team`, { clientId: client.id }), apiFetch<User[]>("/admin/users", { clientId: client.id })]); } catch { canManage = false; }
  return <section className="workspace-section"><SectionHeader title="Team Access" description="Admins can see every client. Add other team members explicitly." /><div className="workspace-panel"><ClientTeamPanel clientId={client.id} clientName={client.client_name} team={team} users={users} canManage={canManage} /></div></section>;
}
