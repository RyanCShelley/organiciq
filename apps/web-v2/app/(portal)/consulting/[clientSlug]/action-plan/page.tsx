import { notFound } from "next/navigation";

import { ActionPlan } from "@/components/portal/ActionPlan";
import { ApiError, apiFetch } from "@/lib/api";
import { getPortals, type ClientRec } from "@/lib/portal";

export const metadata = { title: "Action plan" };

export default async function ActionPlanPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const site = (await getPortals().catch(() => null))?.clients.find((c) => c.slug === clientSlug);
  if (!site) notFound();
  let recs: ClientRec[] = [];
  let error: string | null = null;
  try {
    recs = (await apiFetch<{ recommendations: ClientRec[] }>("/v2/consulting/portal/recommendations", { clientId: site.id })).recommendations;
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The action plan could not be loaded: the API did not answer.";
  }
  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Action plan</h1>
        <p className="mt-1 max-w-2xl text-sm text-[var(--text-secondary)]">What your team can do next, most important first. Open one for the exact steps and how we will know it worked.</p>
      </div>
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : <ActionPlan slug={site.slug} recs={recs} />}
    </section>
  );
}
