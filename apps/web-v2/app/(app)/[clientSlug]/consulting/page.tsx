import Link from "next/link";
import { notFound } from "next/navigation";

import { ConsultingWorkspace } from "@/components/ConsultingWorkspace";
import { ApiError, apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import type { Profile } from "@/lib/portal";

export const metadata = { title: "Consulting workspace" };

export default async function ConsultingPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = await findClient(clientSlug);
  if (!client) notFound();
  if (client.service_mode !== "consulting") {
    return (
      <section className="max-w-2xl space-y-3">
        <h1 className="text-2xl font-bold">Consulting workspace</h1>
        <p className="text-sm text-[var(--text-secondary)]">
          {client.client_name} is an execution client. To give it a consulting portal, set &ldquo;How we work with this client&rdquo; to Consulting in{" "}
          <Link href={`/${client.slug}/settings`} className="font-semibold text-[var(--brand-teal)] hover:underline">Client settings</Link>.
        </p>
      </section>
    );
  }
  let profile: Profile | null = null;
  let error: string | null = null;
  try {
    profile = await apiFetch<Profile>("/v2/consulting/profile", { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The workspace could not be loaded: the API did not answer.";
  }
  return <ConsultingWorkspace client={client} profile={profile} error={error} />;
}
