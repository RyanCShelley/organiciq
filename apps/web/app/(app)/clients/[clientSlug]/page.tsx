import Link from "next/link";
import { ClientAccountSection } from "@/components/ClientAccountSection";
import type { SetupState } from "@/components/SetupChecklist";
import { Alert } from "@/components/ui/Alert";
import { apiFetch } from "@/lib/api";
import { clientHref } from "@/lib/client-path";
import { requireWorkspaceClient } from "@/lib/context";
import { setupProgress } from "@/lib/client-setup";

export default async function ClientSettingsPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = await requireWorkspaceClient(clientSlug);
  let setup: SetupState | null = null;
  try { setup = await apiFetch<SetupState>(`/clients/${client.id}/setup`, { clientId: client.id }); } catch { /* The account stays editable if readiness cannot be checked. */ }
  const progress = setup ? setupProgress(setup) : null;
  return <section className="space-y-6">
    {progress && !progress.complete ? <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 flex flex-wrap items-center justify-between gap-4"><div><h2 className="font-semibold">Finish client setup</h2><p className="text-sm text-[var(--text-secondary)]">{progress.done} of {progress.total} setup stages complete. Continue from the saved configuration.</p></div><Link className="btn btn-primary" href={`${clientHref(client.slug, "setup")}?step=${progress.next}`}>Continue setup</Link></div> : null}
    {!setup ? <Alert variant="warning">Setup status could not be checked. Your saved settings remain available.</Alert> : null}
    <ClientAccountSection client={client} />
  </section>;
}
