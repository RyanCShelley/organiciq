"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { moveReportAction, saveReportAction } from "@/app/(app)/[clientSlug]/consulting/report/actions";
import { card } from "@/components/content/parts";
import { ExecutiveSummary } from "@/components/portal/ExecutiveSummary";
import { ReportDataView } from "@/components/portal/ReportData";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import type { ExecData, Highlights, Notes, ReportData, ReportKind, StaffReport } from "@/lib/portal";

/** The consultant's side of the report: the numbers as they stand, then the analysis in their own words, then publish. */
const NOTE_SECTIONS = [["short_version", "The short version"], ["clicks", "Clicks from Google"], ["topics", "Visibility by topic"], ["competitors", "Against competitors"], ["site_health", "Site health"], ["share_of_voice", "AI share of voice"], ["priorities", "Priorities"]] as const;

export function ReportEditor({ client, month, kind, loaded, error }: { client: Client; month: string; kind: ReportKind; loaded: { report: StaffReport; data: ReportData | ExecData } | null; error: string | null }) {
  const executive = kind === "executive";
  const router = useRouter();
  const [report, setReport] = useState<StaffReport | null>(loaded?.report ?? null);
  const [title, setTitle] = useState(loaded?.report.title ?? "");
  const [analysis, setAnalysis] = useState(loaded?.report.analysis ?? "");
  const lines = (v: string) => v.split("\n").map((l) => l.trim()).filter(Boolean);
  const [notes, setNotes] = useState<Notes>(loaded?.report.notes ?? {});
  const [lists, setLists] = useState<Record<keyof Highlights, string>>({
    going_well: (loaded?.report.highlights?.going_well ?? []).join("\n"),
    to_watch: (loaded?.report.highlights?.to_watch ?? []).join("\n"),
    gaps: (loaded?.report.highlights?.gaps ?? []).join("\n"),
  });
  const highlights = (): Highlights => ({ going_well: lines(lists.going_well), to_watch: lines(lists.to_watch), gaps: lines(lists.gaps) });
  const hasWords = !!analysis.trim() || Object.values(lists).some((v) => v.trim());
  const [pending, start] = useTransition();
  const [saved, setSaved] = useState(false);
  const [problem, setProblem] = useState<string | null>(error);
  const published = report?.review_state === "published";
  const apply = (r: { ok: true; value: StaffReport } | { ok: false; error: string }) => { if (r.ok) { setReport(r.value); setProblem(null); setSaved(true); } else setProblem(r.error); };
  const body = () => ({ analysis, title, highlights: highlights(), notes: executive ? notes : undefined, kind });
  const save = () => start(async () => apply(await saveReportAction(client.id, client.slug, month, { ...body(), revision: report?.exists ? report.revision : null })));
  const publish = () => start(async () => {
    const s = await saveReportAction(client.id, client.slug, month, { ...body(), revision: report?.exists ? report.revision : null });
    if (!s.ok) return apply(s);
    apply(await moveReportAction(client.id, client.slug, month, "published", kind));
  });
  const unpublish = () => start(async () => apply(await moveReportAction(client.id, client.slug, month, "draft", kind)));
  return (
    <section className="max-w-5xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{executive ? "Executive summary" : "Monthly performance report"}</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{client.client_name}. The numbers, then your analysis in your own words. The client sees them together, above the action plan.</p>
        </div>
        <div className="flex items-center gap-2">
          <div role="tablist" aria-label="Report type" className="flex rounded-lg border border-[var(--border)] bg-white p-0.5 text-sm font-semibold">
            {([["executive", "Executive summary"], ["monthly", "Monthly performance"]] as const).map(([k, l]) => (
              <button key={k} type="button" role="tab" aria-selected={kind === k} onClick={() => router.push(`/${client.slug}/consulting/report?month=${month}&kind=${k}`)} className={`rounded-md px-3 py-1.5 ${kind === k ? "bg-[var(--brand-navy)] text-white" : "text-[var(--text-secondary)]"}`}>{l}</button>
            ))}
          </div>
          <input type="month" value={month} onChange={(e) => e.target.value && router.push(`/${client.slug}/consulting/report?month=${e.target.value}&kind=${kind}`)} aria-label="Month" className="rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm" />
          <Link href={`/consulting/${client.slug}`} className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold text-[var(--brand-teal)] hover:underline">Preview as client</Link>
        </div>
      </header>
      {problem ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{problem}</p> : null}

      <section>
        <h2 className="mb-1 text-lg font-bold">1. The data</h2>
        <p className="mb-3 text-xs text-[var(--text-secondary)]">{published ? "Frozen as it was when you published. Unpublish and publish again to refresh it." : "Live from the monthly review. These freeze when you publish."}</p>
        {loaded ? (executive ? <ExecutiveSummary report={{ kind: "executive", month, title: title || null, analysis: analysis || null, highlights: highlights(), notes, published_at: report?.published_at ?? null, data: loaded.data as ExecData }} /> : <ReportDataView data={loaded.data as ReportData} />) : null}
      </section>

      <section className={`${card} space-y-3 p-5`}>
        <h2 className="text-lg font-bold">2. Your analysis</h2>
        <label className="block text-sm font-semibold">Headline <span className="font-normal text-[var(--text-secondary)]">(optional)</span><span className="block text-xs font-normal text-[var(--text-secondary)]">State the finding: “October 2026: demo requests up 37% while SD-WAN terms dropped out of the top 100”.</span>
          <input value={title} onChange={(e) => { setTitle(e.target.value); setSaved(false); }} placeholder={`${new Date(`${month}-01T00:00:00`).toLocaleDateString("en-US", { month: "long", year: "numeric" })} report`} className="mt-1 block w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm font-normal" />
        </label>
        <label className="block text-sm font-semibold">Short intro <span className="font-normal text-[var(--text-secondary)]">(optional)</span>
          <span className="block text-xs font-normal text-[var(--text-secondary)]">A few sentences: what happened this month and why it matters. Leave a blank line between paragraphs.</span>
          <textarea value={analysis} onChange={(e) => { setAnalysis(e.target.value); setSaved(false); }} rows={5} className="mt-1 block w-full rounded-lg border border-[var(--border)] bg-white p-3 text-sm font-normal leading-6" />
        </label>
        <div className="grid gap-4 lg:grid-cols-3">
          {([
            ["going_well", "Going well", "bg-green-50 border-green-200", "What is working. One point per line."],
            ["to_watch", "To watch", "bg-amber-50 border-amber-200", "What may become a problem."],
            ["gaps", "Biggest gaps", "bg-red-50 border-red-200", "Where the biggest opportunity or risk is."],
          ] as const).map(([key, label, cls, hint]) => (
            <label key={key} className={`block rounded-xl border p-3 text-sm font-semibold ${cls}`}>{label}
              <span className="block text-xs font-normal text-[var(--text-secondary)]">{hint}</span>
              <textarea value={lists[key]} onChange={(e) => { setLists({ ...lists, [key]: e.target.value }); setSaved(false); }} rows={8} className="mt-2 block w-full rounded-lg border border-[var(--border)] bg-white p-2.5 text-sm font-normal leading-6" />
            </label>
          ))}
        </div>
        {executive ? (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">A line of context under each part <span className="font-normal text-[var(--text-secondary)]">(optional)</span></h3>
            <div className="grid gap-3 sm:grid-cols-2">
              {NOTE_SECTIONS.map(([key, label]) => (
                <label key={key} className="block text-xs font-semibold">{label}
                  <textarea value={notes[key] ?? ""} onChange={(e) => { setNotes({ ...notes, [key]: e.target.value }); setSaved(false); }} rows={2} maxLength={1500} className="mt-1 block w-full rounded-lg border border-[var(--border)] bg-white p-2.5 text-sm font-normal leading-6" />
                </label>
              ))}
            </div>
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={save} disabled={pending} className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold disabled:opacity-50">{pending ? <><Spinner />Saving…</> : "Save draft"}</button>
          {published ? (
            <button type="button" onClick={unpublish} disabled={pending} className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold disabled:opacity-50">Unpublish (hide from the client)</button>
          ) : null}
          <button type="button" onClick={publish} disabled={pending || !hasWords} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{published ? "Publish again with today's numbers" : "Publish to client"}</button>
          {saved ? <span className="text-sm text-green-800">Saved.</span> : null}
        </div>
        <p className="text-xs text-[var(--text-secondary)]">{published ? `Published ${report?.published_at?.slice(0, 10)} by ${report?.published_by}.` : "Not visible to the client until you publish."} Publishing shows the report only: it creates no work for SMA.</p>
      </section>
    </section>
  );
}
