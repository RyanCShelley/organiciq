import Link from "next/link";

import { ActionPlan } from "@/components/portal/ActionPlan";
import { Analysis } from "@/components/portal/Analysis";
import { card } from "@/components/portal/BriefParts";
import { ExecutiveSummary } from "@/components/portal/ExecutiveSummary";
import { ReportDataView } from "@/components/portal/ReportData";
import { ApiError, apiFetch } from "@/lib/api";
import { IMPL_LABEL, getPortals, type ClientRec, type ClientReport, type PortalOverview, type PortalReports } from "@/lib/portal";

export const metadata = { title: "Consulting portal" };

const monthName = (m: string) => new Date(`${m}-01T00:00:00`).toLocaleDateString("en-US", { month: "long", year: "numeric" });

/** The portal's front page reads as a report: the numbers, then your consultant's analysis of them, then what to do. */
const VIEWS = [{ key: "executive", label: "Executive summary" }, { key: "monthly", label: "Monthly performance" }, { key: "plan", label: "Action plan" }] as const;

export default async function PortalDashboard({ params, searchParams }: { params: Promise<{ clientSlug: string }>; searchParams: Promise<{ view?: string }> }) {
  const { clientSlug } = await params;
  const { view: asked } = await searchParams;
  const site = (await getPortals().catch(() => null))?.clients.find((c) => c.slug === clientSlug);
  let ov: PortalOverview | null = null;
  let reports: PortalReports = { monthly: null, executive: null };
  let recs: ClientRec[] = [];
  let error: string | null = null;
  if (site) {
    try {
      [ov, reports, recs] = await Promise.all([
        apiFetch<PortalOverview>("/v2/consulting/portal/overview", { clientId: site.id }),
        apiFetch<PortalReports>("/v2/consulting/portal/reports", { clientId: site.id }),
        apiFetch<{ recommendations: ClientRec[] }>("/v2/consulting/portal/recommendations", { clientId: site.id }).then((r) => r.recommendations),
      ]);
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The portal could not be loaded: the API did not answer.";
    }
  }
  const report: ClientReport | null = reports.monthly;
  const view = VIEWS.some((v) => v.key === asked) ? (asked as (typeof VIEWS)[number]["key"]) : reports.executive ? "executive" : report ? "monthly" : "plan";
  const tabs = (
    <nav aria-label="Report" className="flex flex-wrap gap-1 border-b border-[var(--border)]">
      {VIEWS.map((v) => (
        <Link key={v.key} href={`/consulting/${clientSlug}?view=${v.key}`} aria-current={view === v.key ? "page" : undefined} className={`-mb-px border-b-2 px-3 py-2 text-sm font-semibold ${view === v.key ? "border-[var(--brand-teal)] text-[var(--brand-teal)]" : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}>{v.label}</Link>
      ))}
    </nav>
  );
  if (view === "executive")
    return (
      <section className="mx-auto max-w-4xl space-y-8">
        {tabs}
        {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
        {reports.executive ? <ExecutiveSummary report={reports.executive} /> : <p className={`${card} p-5 text-sm text-[var(--text-secondary)]`}>No executive summary has been published yet.</p>}
      </section>
    );
  return (
    <section className="mx-auto max-w-3xl space-y-12">
      {tabs}
      <div>
        <h1 className="text-2xl font-bold">{report ? (report.title || `${monthName(report.month)} report`) : `Welcome${site ? `, ${site.name}` : ""}`}</h1>
        <p className="mt-1 max-w-2xl text-sm text-[var(--text-secondary)]">{report ? `Prepared by your consultant · published ${report.published_at?.slice(0, 10)}` : "Where your consultant shares what changed in your search and AI visibility, traffic and leads, why it matters, and what your team can do next."}</p>
      </div>
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}

      {view === "monthly" && !report ? <p className={`${card} p-5 text-sm text-[var(--text-secondary)]`}>No monthly report has been published yet.</p> : null}
      {view === "monthly" && report ? (
        <>
          <section>
            <h2 className="mb-3 text-lg font-bold">1. The data</h2>
            <ReportDataView data={report.data} />
          </section>
          {report.analysis || Object.values(report.highlights ?? {}).some((l) => l.length) ? (
            <section>
              <h2 className="mb-3 text-lg font-bold">2. What it means</h2>
              <Analysis intro={report.analysis} highlights={report.highlights ?? { going_well: [], to_watch: [], gaps: [] }} />
            </section>
          ) : null}
        </>
      ) : null}

      {view === "plan" && ov && site ? (
        <section>
          <div className="mb-3 flex items-baseline justify-between"><h2 className="text-lg font-bold">Action plan</h2>{ov.total ? <Link href={`/consulting/${site.slug}/action-plan`} className="text-sm font-semibold text-[var(--brand-teal)] hover:underline">Open the action plan</Link> : null}</div>
          {ov.total > 0 ? (
            <>
              <div className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                {(["recommended", "planned", "in_progress", "completed", "blocked"] as const).map((k) => (
                  <div key={k} className={`${card} p-3`}><div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">{IMPL_LABEL[k]}</div><div className="mt-1 text-2xl font-bold tabular-nums">{ov.counts[k]}</div></div>
                ))}
              </div>
              <p className="mb-3 text-xs text-[var(--text-secondary)]">{ov.not_reported} of {ov.total} have no update from your team yet{ov.verified ? `; ${ov.verified} confirmed on the live page` : ""}. We can only count what we are told or can see.</p>
              <ActionPlan slug={site.slug} recs={recs} />
            </>
          ) : (
            <p className={`${card} p-5 text-sm text-[var(--text-secondary)]`}>Nothing has been published yet.</p>
          )}
        </section>
      ) : null}
    </section>
  );
}
