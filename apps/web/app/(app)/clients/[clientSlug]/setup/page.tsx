import Link from "next/link";
import { ClientAccountSection } from "@/components/ClientAccountSection";
import { ClientGoalsSection } from "@/components/ClientGoalsSection";
import { SetupFinishButton } from "@/components/SetupFinishButton";
import type { SetupState } from "@/components/SetupChecklist";
import { SyncAll90DaysPanel } from "@/components/SyncAll90DaysPanel";
import { Alert } from "@/components/ui/Alert";
import { apiFetch, type Integration } from "@/lib/api";
import { clientHref } from "@/lib/client-path";
import { requireWorkspaceClient } from "@/lib/context";
import { setupProgress } from "@/lib/client-setup";
import { ClientConnections } from "@/components/ClientConnectionsSection";
import { ClientConversionsContent } from "@/components/ClientConversionsSection";
import { ClientMappingContent } from "@/components/ClientMappingSection";

export default async function ClientSetupPage({ params, searchParams }: { params: Promise<{ clientSlug: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { clientSlug } = await params; const query = await searchParams;
  const client = await requireWorkspaceClient(clientSlug, "setup");
  let setup: SetupState;
  try { setup = await apiFetch<SetupState>(`/clients/${client.id}/setup`, { clientId: client.id }); } catch { return <Alert variant="danger">Setup status could not be loaded. Reload to continue; existing settings are unchanged.</Alert>; }
  const progress = setupProgress(setup);
  const requested = typeof query.step === "string" && /^\d$/.test(query.step) ? Number(query.step) : progress.next;
  const step = Math.min(6, Math.max(0, requested));
  const href = (n: number) => `${clientHref(client.slug, "setup")}?step=${n}`;
  const current = progress.stages[step];
  let integrations: Integration[] = [];
  if (step === 2) { try { integrations = await apiFetch<Integration[]>("/integrations", { clientId: client.id }); } catch { return <Alert variant="danger">Connections could not be loaded. Reload before starting syncs.</Alert>; } }
  const has = (p: string) => integrations.some(i => i.provider === p && i.connection_status === "connected" && i.external_property_id);
  const requiredReady = progress.stages.slice(0, 5).every(s => s.done);
  return <div className="mx-auto max-w-5xl space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-2xl font-bold">Set up {client.client_name}</h2><p className="mt-1 text-sm text-[var(--text-secondary)]">Saved configuration determines progress. You can return without starting over.</p></div><Link href={clientHref(client.slug)} className="btn btn-secondary">Back to settings</Link></div>
    <nav aria-label="Setup progress" className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">{progress.stages.map((s, i) => <Link key={s.label} href={href(i)} aria-current={i === step ? "step" : undefined} className={`border-t-4 px-2 py-3 text-xs ${i === step ? "border-[var(--brand-teal)] font-bold text-[var(--brand-teal)]" : s.done ? "border-emerald-500 text-[var(--text-secondary)]" : "border-[var(--border)] text-[var(--text-secondary)]"}`}>{s.done ? "✓" : i + 1}. {s.label}</Link>)}</nav>
    {step === 0 ? <ClientAccountSection client={client} continueHref={href(1)} /> : null}
    {step === 1 ? <ClientConnections client={client} showSync={false} /> : null}
    {step === 2 ? <><h2 className="section-title">Bring in the first data</h2><p className="text-sm text-[var(--text-secondary)]">Property selection starts reporting syncs automatically. Start the full initial pull to include the current site crawl. Unavailable history or a blocked crawl is a measurement limit, not a site defect.</p><SyncAll90DaysPanel clientId={client.id} hasGa4Property={has("ga4")} hasGscProperty={has("gsc")} hasSerankingProject={has("se_ranking")} hasDomain={Boolean(client.domain)} compact /></> : null}
    {step === 3 ? <ClientConversionsContent client={client} includeGoals={false} /> : null}
    {step === 4 ? <ClientMappingContent client={client} /> : null}
    {step === 5 ? <ClientGoalsSection client={client} /> : null}
    {step === 6 ? <section className="workspace-panel space-y-5"><h2 className="section-title">Review & finish</h2>{progress.stages.slice(0,6).map((s,i) => <div className="flex items-center justify-between border-b border-[var(--border)] pb-3 text-sm" key={s.label}><Link href={href(i)} className="underline">{s.label}</Link><span>{s.done ? "Saved" : i === 5 ? "Review later" : "Needs attention"}</span></div>)}<SetupFinishButton clientId={client.id} slug={client.slug} ready={requiredReady} alreadyRun={progress.stages[6].done} /></section> : null}
    {step < 6 ? <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border)] pt-5"><div>{step > 0 ? <Link className="btn btn-secondary" href={href(step-1)}>Back</Link> : null}</div><p className="text-xs text-[var(--text-secondary)]">Step {step+1} of 7 · {step === 5 ? "Baseline locking requires explicit review" : "Save changes in each section before continuing"}</p>{step > 0 ? current.done || step === 5 ? <Link className="btn btn-primary" href={href(step+1)}>{step === 5 && !current.done ? "Review later & continue" : "Continue"}</Link> : <Link href={href(step)} className="btn btn-secondary">Check saved progress</Link> : null}</footer> : null}
  </div>;
}
