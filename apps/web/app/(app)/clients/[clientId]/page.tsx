import Link from "next/link";
import { notFound } from "next/navigation";

import { ClientWorkspaceNav } from "@/components/ClientWorkspaceNav";
import { apiFetch, type DataHealthRow } from "@/lib/api";
import { loadClientById } from "@/lib/context";

export default async function ClientWorkspaceHomePage({
  params,
}: {
  params: Promise<{ clientId: string }>;
}) {
  const { clientId } = await params;
  const client = await loadClientById(clientId);
  if (!client) notFound();

  let health: DataHealthRow[] = [];
  try {
    health = await apiFetch<DataHealthRow[]>("/admin/data-health", { clientId });
  } catch {
    health = [];
  }

  const healthy = health.filter((row) => row.status === "Healthy").length;

  return (
    <section>
      <ClientWorkspaceNav clientId={clientId} active={`/clients/${clientId}`} />
      <h1 className="text-2xl font-semibold">Workspace Overview</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Configure this client&apos;s integrations and conversions, then monitor sync health here.
      </p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <WorkspaceCard
          href={`/clients/${clientId}/integrations`}
          title="Integrations"
          description="Google OAuth, GSC, GA4, SE Ranking"
        />
        <WorkspaceCard
          href={`/clients/${clientId}/conversions`}
          title="Conversions"
          description="Map GA4 events to leads"
        />
        <WorkspaceCard
          href={`/clients/${clientId}/data-health`}
          title="Data Health"
          description={`${healthy}/${health.length || 5} sources healthy`}
        />
        <WorkspaceCard
          href={`/clients/${clientId}/jobs`}
          title="Sync Jobs"
          description="Enqueue and review ingestion"
        />
      </div>
    </section>
  );
}

function WorkspaceCard({
  href,
  title,
  description,
}: {
  href: string;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 hover:border-[var(--accent)]"
    >
      <div className="font-medium">{title}</div>
      <div className="mt-1 text-sm text-[var(--muted)]">{description}</div>
    </Link>
  );
}
