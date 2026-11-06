import Link from "next/link";

import { ActionPlan } from "@/components/portal/ActionPlan";
import { card } from "@/components/portal/BriefParts";
import { ApiError, apiFetch } from "@/lib/api";
import { IMPL_LABEL, getPortals, type PortalOverview } from "@/lib/portal";

export const metadata = { title: "Consulting portal" };

export default async function PortalDashboard({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const site = (await getPortals().catch(() => null))?.clients.find((c) => c.slug === clientSlug);
  let ov: PortalOverview | null = null;
  let error: string | null = null;
  if (site) {
    try {
      ov = await apiFetch<PortalOverview>("/v2/consulting/portal/overview", { clientId: site.id });
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The overview could not be loaded: the API did not answer.";
    }
  }
  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Welcome{site ? `, ${site.name}` : ""}</h1>
        <p className="mt-1 max-w-2xl text-sm text-[var(--text-secondary)]">Where your consultant shares what changed in your search and AI visibility, traffic and leads, why it matters, and what your team can do next.</p>
      </div>
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      {ov && ov.total === 0 ? <p className={`${card} p-5 text-sm text-[var(--text-secondary)]`}>Nothing has been published yet.</p> : null}
      {ov && ov.total > 0 && site ? (
        <>
          <section>
            <h2 className="mb-2 text-lg font-bold">Implementation progress</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {(["recommended", "planned", "in_progress", "completed", "blocked"] as const).map((k) => (
                <div key={k} className={`${card} p-4`}><div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">{IMPL_LABEL[k]}</div><div className="mt-1 text-3xl font-bold tabular-nums">{ov.counts[k]}</div></div>
              ))}
            </div>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">{ov.not_reported} of {ov.total} have no update from your team yet{ov.verified ? `; ${ov.verified} confirmed on the live page` : ""}. We can only count what we are told or can see.</p>
          </section>
          <section>
            <div className="mb-2 flex items-baseline justify-between"><h2 className="text-lg font-bold">Priority opportunities</h2><Link href={`/consulting/${site.slug}/action-plan`} className="text-sm font-semibold text-[var(--brand-teal)] hover:underline">See the whole action plan</Link></div>
            <ActionPlan slug={site.slug} recs={ov.top} />
          </section>
        </>
      ) : null}
    </section>
  );
}
