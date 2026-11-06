import Link from "next/link";

import { ActionPlan } from "@/components/portal/ActionPlan";
import { card } from "@/components/portal/BriefParts";
import { ReportDataView } from "@/components/portal/ReportData";
import { ApiError, apiFetch } from "@/lib/api";
import { IMPL_LABEL, getPortals, type ClientRec, type ClientReport, type PortalOverview } from "@/lib/portal";

export const metadata = { title: "Consulting portal" };

const monthName = (m: string) => new Date(`${m}-01T00:00:00`).toLocaleDateString("en-US", { month: "long", year: "numeric" });

/** The portal's front page reads as a report: the numbers, then your consultant's analysis of them, then what to do. */
export default async function PortalDashboard({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const site = (await getPortals().catch(() => null))?.clients.find((c) => c.slug === clientSlug);
  let ov: PortalOverview | null = null;
  let report: ClientReport | null = null;
  let recs: ClientRec[] = [];
  let error: string | null = null;
  if (site) {
    try {
      [ov, report, recs] = await Promise.all([
        apiFetch<PortalOverview>("/v2/consulting/portal/overview", { clientId: site.id }),
        apiFetch<{ report: ClientReport | null }>("/v2/consulting/portal/report", { clientId: site.id }).then((r) => r.report),
        apiFetch<{ recommendations: ClientRec[] }>("/v2/consulting/portal/recommendations", { clientId: site.id }).then((r) => r.recommendations),
      ]);
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The portal could not be loaded: the API did not answer.";
    }
  }
  return (
    <section className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">{report ? (report.title || `${monthName(report.month)} report`) : `Welcome${site ? `, ${site.name}` : ""}`}</h1>
        <p className="mt-1 max-w-2xl text-sm text-[var(--text-secondary)]">{report ? `Prepared by your consultant · published ${report.published_at?.slice(0, 10)}` : "Where your consultant shares what changed in your search and AI visibility, traffic and leads, why it matters, and what your team can do next."}</p>
      </div>
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}

      {report ? (
        <>
          <section>
            <h2 className="mb-3 text-lg font-bold">1. The data</h2>
            <ReportDataView data={report.data} />
          </section>
          {report.analysis ? (
            <section>
              <h2 className="mb-3 text-lg font-bold">2. What it means</h2>
              <div className={`${card} p-6`}><p className="max-w-3xl whitespace-pre-line text-[0.95rem] leading-7">{report.analysis}</p></div>
            </section>
          ) : null}
        </>
      ) : null}

      {ov && site ? (
        <section>
          <div className="mb-3 flex items-baseline justify-between"><h2 className="text-lg font-bold">{report ? "3. What to do next" : "Action plan"}</h2>{ov.total ? <Link href={`/consulting/${site.slug}/action-plan`} className="text-sm font-semibold text-[var(--brand-teal)] hover:underline">Open the action plan</Link> : null}</div>
          {ov.total > 0 ? (
            <>
              <div className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                {(["recommended", "planned", "in_progress", "completed", "blocked"] as const).map((k) => (
                  <div key={k} className={`${card} p-3`}><div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">{IMPL_LABEL[k]}</div><div className="mt-1 text-2xl font-bold tabular-nums">{ov.counts[k]}</div></div>
                ))}
              </div>
              <p className="mb-3 text-xs text-[var(--text-secondary)]">{ov.not_reported} of {ov.total} have no update from your team yet{ov.verified ? `; ${ov.verified} confirmed on the live page` : ""}. We can only count what we are told or can see.</p>
              <ActionPlan slug={site.slug} recs={report ? recs : ov.top} />
            </>
          ) : (
            <p className={`${card} p-5 text-sm text-[var(--text-secondary)]`}>Nothing has been published yet.</p>
          )}
        </section>
      ) : null}
    </section>
  );
}
