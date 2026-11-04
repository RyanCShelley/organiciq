import { notFound } from "next/navigation";

import { TeamAccess, type TeamMember, type StaffUser } from "@/components/TeamAccess";
import { ApiError, apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";

export const metadata = { title: "Settings · Team access" };

export default async function TeamPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  try {
    const [team, users] = await Promise.all([
      apiFetch<TeamMember[]>(`/admin/clients/${client.id}/team`),
      apiFetch<StaffUser[]>("/admin/users"),
    ]);
    return <TeamAccess clientId={client.id} slug={client.slug} team={team} users={users} />;
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return (
        <p className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-sm text-[var(--text-secondary)]">
          Only an admin can see or change who has access to a client.
        </p>
      );
    }
    throw error;
  }
}
