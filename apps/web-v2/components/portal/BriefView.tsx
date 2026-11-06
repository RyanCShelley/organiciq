"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { updateProgressAction } from "@/app/(portal)/consulting/[clientSlug]/action-plan/actions";
import { Chips, StatusLine, card } from "@/components/portal/BriefParts";
import type { ClientRec } from "@/lib/portal";

const STATES = [{ k: "planned", l: "Planned" }, { k: "in_progress", l: "In progress" }, { k: "completed", l: "Completed" }, { k: "blocked", l: "Blocked" }] as const;
const input = "rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm";

function Block({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">{label}</p>{children}</div>;
}

/** One recommendation, written for the client's team: what we found, why it matters, exactly what to do, and how we will know. */
export function BriefView({ clientId, slug, rec: first }: { clientId: string; slug: string; rec: ClientRec }) {
  const [rec, setRec] = useState(first);
  const [status, setStatus] = useState(first.impl_status === "recommended" ? "planned" : first.impl_status);
  const [date, setDate] = useState(first.implemented_on ?? "");
  const [estimated, setEstimated] = useState(first.implemented_on_estimated);
  const [notes, setNotes] = useState(first.client_notes ?? "");
  const [links, setLinks] = useState(first.evidence_links.join("\n"));
  const [pending, start] = useTransition();
  const [saved, setSaved] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const save = () =>
    start(async () => {
      const r = await updateProgressAction(clientId, slug, rec.id, { status, implemented_on: date || null, estimated: estimated && !!date, notes, links: links.split("\n").map((l) => l.trim()).filter(Boolean) });
      if (r.ok) { setRec({ ...r.value }); setSaved(true); setProblem(null); } else setProblem(r.error);
    });
  const m = rec.success_metrics[0];
  return (
    <article className="space-y-6">
      <Link href={`/consulting/${slug}/action-plan`} className="text-sm font-semibold text-[var(--brand-teal)] hover:underline">← Action plan</Link>
      <div className={`${card} space-y-5 p-6`}>
        <div className="space-y-2">
          <Chips rec={rec} />
          <h1 className="text-2xl font-bold">{rec.title}</h1>
          <div className="flex flex-wrap items-center gap-3 text-sm text-[var(--text-secondary)]">
            {rec.owner ? <span>Owner: {rec.owner}</span> : null}
            {rec.effort_min ? <span>About {rec.effort_min} minutes</span> : null}
          </div>
          {rec.target_urls.length ? (
            <ul className="space-y-1 text-sm">
              {rec.target_urls.map((u) => (
                <li key={u.url} className="break-all">
                  <a href={u.live_url || u.url} target="_blank" rel="noreferrer" className="text-[var(--brand-teal)] hover:underline">{u.live_url || u.url}</a>
                  {u.state === "exists" || u.state === "canonical" ? <span className="ml-2 rounded bg-green-50 px-1.5 py-0.5 text-xs font-semibold text-green-800">Live page confirmed</span> : u.state === "new" ? <span className="ml-2 rounded bg-[var(--bg)] px-1.5 py-0.5 text-xs">New page</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        {m || rec.expected_impact ? (
          <div className="grid gap-3 sm:grid-cols-3">
            {m ? <div className="rounded-lg bg-[var(--background)] p-3"><div className="text-xs text-[var(--text-secondary)]">{m.metric}</div><div className="text-lg font-semibold">{m.baseline || "–"}{m.target ? ` → ${m.target}` : ""}</div>{m.window_days ? <div className="text-xs text-[var(--text-secondary)]">checked {m.window_days} days after you publish</div> : null}</div> : null}
            {rec.expected_impact ? <div className="rounded-lg bg-[var(--background)] p-3"><div className="text-xs text-[var(--text-secondary)]">Expected impact · confidence</div><div className="text-sm font-semibold">{rec.expected_impact}</div><div className="text-xs text-[var(--text-secondary)]">{rec.confidence[0].toUpperCase() + rec.confidence.slice(1)} confidence. An estimate, not a promise.</div></div> : null}
            {rec.measure_on ? <div className="rounded-lg bg-[var(--background)] p-3"><div className="text-xs text-[var(--text-secondary)]">We will check on</div><div className="text-lg font-semibold">{rec.measure_on}</div></div> : null}
          </div>
        ) : null}

        {rec.finding ? <Block label="What we found"><p>{rec.finding}</p></Block> : null}
        {rec.explanation ? (
          <Block label="Why it matters">
            <p>{rec.explanation}</p>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">{rec.cause_kind === "confirmed" ? "Confirmed by two independent signals." : "Our best explanation, not yet confirmed."}{rec.cause_text ? ` ${rec.cause_text}` : ""}</p>
          </Block>
        ) : null}
        {rec.action ? <Block label="What to do"><p className="font-medium">{rec.action}</p></Block> : null}
        {rec.instructions.length ? (
          <Block label="Steps">
            <ul className="space-y-1 rounded-lg border border-[var(--border)] p-3 text-sm leading-7">{rec.instructions.map((i, n) => <li key={n}>☐ {i.text}</li>)}</ul>
          </Block>
        ) : null}
        {rec.evidence.length ? (
          <Block label="Evidence">
            <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--text-secondary)]">{rec.evidence.map((e, n) => <li key={n}>{e.text}{e.source ? <span className="text-[var(--text-tertiary)]"> ({e.source}{e.as_of ? `, ${e.as_of}` : ""})</span> : null}</li>)}</ul>
          </Block>
        ) : null}

        <Block label="Where this stands">
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {["Recommended", "Approved"].map((s) => <span key={s} className="rounded-lg bg-green-50 px-3 py-1 font-semibold text-green-800">{s}</span>)}
            <span className="text-[var(--text-tertiary)]">→</span>
            <span className={`rounded-lg px-3 py-1 font-semibold ${rec.reported ? "bg-[var(--bg-accent,#e6f1fb)] text-[var(--brand-teal)]" : "bg-[var(--bg)] text-[var(--text-secondary)]"}`}>{rec.reported ? `Implementation: ${STATES.find((s) => s.k === rec.impl_status)?.l ?? "Recommended"}` : "Implementation: not reported yet"}</span>
            <span className="text-[var(--text-tertiary)]">→</span>
            <span className={`rounded-lg px-3 py-1 font-semibold ${rec.verification === "verified" ? "bg-green-50 text-green-800" : "bg-[var(--bg)] text-[var(--text-secondary)]"}`}>{rec.verification === "verified" ? "Verified on the live page" : "Not yet verified"}</span>
            <span className="text-[var(--text-tertiary)]">→</span>
            <span className="rounded-lg bg-[var(--bg)] px-3 py-1 font-semibold text-[var(--text-secondary)]">Not yet measured</span>
          </div>
          <div className="mt-2"><StatusLine rec={rec} />{rec.implemented_on ? <span className="ml-2 text-xs text-[var(--text-secondary)]">Went live {rec.implemented_on}{rec.implemented_on_estimated ? " (estimated)" : ""}</span> : null}</div>
        </Block>

        {rec.can_update ? (
          <div className="space-y-3 rounded-lg border border-[var(--border)] p-4">
            <p className="text-sm font-semibold">Tell us where this stands</p>
            <div className="flex flex-wrap items-center gap-2">
              <select value={status} onChange={(e) => { setStatus(e.target.value as typeof status); setSaved(false); }} className={input}>{STATES.map((s) => <option key={s.k} value={s.k}>{s.l}</option>)}</select>
              <label className="flex items-center gap-2 text-sm">Date it went live<input type="date" value={date} onChange={(e) => { setDate(e.target.value); setSaved(false); }} className={input} /></label>
              <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={estimated} onChange={(e) => setEstimated(e.target.checked)} /> approximate</label>
            </div>
            <textarea value={notes} onChange={(e) => { setNotes(e.target.value); setSaved(false); }} rows={2} placeholder="A note for your consultant" className={`${input} w-full`} />
            <textarea value={links} onChange={(e) => { setLinks(e.target.value); setSaved(false); }} rows={2} placeholder="Links that show it (one per line)" className={`${input} w-full font-mono`} />
            <div className="flex items-center gap-3">
              <button type="button" onClick={save} disabled={pending} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{pending ? "Saving…" : "Save"}</button>
              {saved ? <span className="text-sm text-green-800">Saved. Your consultant can see this.</span> : null}
              {problem ? <span role="alert" className="text-sm text-red-800">{problem}</span> : null}
            </div>
          </div>
        ) : null}
        <p className="text-xs text-[var(--text-secondary)]">Prepared by SMA Marketing · powered by Organic IQ. Changes in your numbers after the work is done may not be caused by this work alone.</p>
      </div>
    </article>
  );
}
