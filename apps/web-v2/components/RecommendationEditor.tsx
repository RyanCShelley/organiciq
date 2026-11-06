"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { createRecAction, followUpRecAction, moveRecAction, progressRecAction, saveRecAction, verifyRecAction } from "@/app/(app)/[clientSlug]/consulting/recommendations/actions";
import { card } from "@/components/content/parts";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import { IMPL_LABEL, STATE_LABEL, type Rec, type RecState } from "@/lib/portal";

const input = "mt-1 block w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm font-normal";
const lines = (v: string) => v.split("\n").map((l) => l.trim()).filter(Boolean);
const text = (v: string | null | undefined) => v ?? "";

type Form = {
  title: string; category: string; focus: string; priority: string; confidence: string; cause_kind: string; cause_text: string; finding: string; explanation: string; action: string;
  instructions: string; target_urls: string; expected_impact: string; confidence_reasons: string; effort_min: string; owner: string; measure_on: string;
  metric: string; metric_baseline: string; metric_target: string; metric_days: string; evidence: string; internal_notes: string;
};

function fromRec(rec: Rec | null): Form {
  const m = rec?.success_metrics?.[0];
  return {
    title: text(rec?.title), category: rec?.category ?? "visibility", focus: rec?.focus ?? "seo", priority: rec?.priority ?? "medium", confidence: rec?.confidence ?? "medium",
    cause_kind: rec?.cause_kind ?? "hypothesis", cause_text: text(rec?.cause_text), finding: text(rec?.finding), explanation: text(rec?.explanation), action: text(rec?.action),
    instructions: (rec?.instructions ?? []).map((i) => i.text).join("\n"), target_urls: (rec?.target_urls ?? []).map((u) => u.url).join("\n"), expected_impact: text(rec?.expected_impact),
    confidence_reasons: (rec?.confidence_reasons ?? []).join("\n"), effort_min: rec?.effort_min != null ? String(rec.effort_min) : "", owner: text(rec?.owner), measure_on: text(rec?.measure_on),
    metric: text(m?.metric), metric_baseline: text(m?.baseline), metric_target: text(m?.target), metric_days: m?.window_days != null ? String(m.window_days) : "",
    evidence: (rec?.evidence ?? []).map((e) => (e.source ? `${e.text} | ${e.source}` : e.text)).join("\n"), internal_notes: text(rec?.internal_notes),
  };
}

function toBody(f: Form) {
  return {
    title: f.title, category: f.category, focus: f.focus, priority: f.priority, confidence: f.confidence, cause_kind: f.cause_kind, cause_text: f.cause_text, finding: f.finding,
    explanation: f.explanation, action: f.action, instructions: lines(f.instructions).map((t) => ({ text: t })), target_urls: lines(f.target_urls),
    expected_impact: f.expected_impact, confidence_reasons: lines(f.confidence_reasons), effort_min: f.effort_min ? Number(f.effort_min) : null, owner: f.owner,
    measure_on: f.measure_on || null,
    success_metrics: f.metric ? [{ metric: f.metric, baseline: f.metric_baseline, target: f.metric_target, window_days: f.metric_days ? Number(f.metric_days) : undefined }] : [],
    evidence: lines(f.evidence).map((l) => { const [t, s] = l.split("|").map((p) => p.trim()); return s ? { text: t, source: s } : { text: t }; }),
    internal_notes: f.internal_notes,
  };
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <label className="block text-sm font-semibold">{label}{hint ? <span className="block text-xs font-normal text-[var(--text-secondary)]">{hint}</span> : null}{children}</label>;
}

export function RecommendationEditor({ client, rec: first, error: loadError }: { client: Client; rec: Rec | null; error: string | null }) {
  const router = useRouter();
  const [rec, setRec] = useState<Rec | null>(first);
  const [f, setF] = useState<Form>(() => fromRec(first));
  const [pending, start] = useTransition();
  const [problem, setProblem] = useState<string | null>(loadError);
  const [saved, setSaved] = useState(false);
  const set = (k: keyof Form) => (e: { target: { value: string } }) => { setF({ ...f, [k]: e.target.value }); setSaved(false); };
  const back = `/${client.slug}/consulting/recommendations`;

  const [prog, setProg] = useState({ status: first?.impl_status ?? "recommended", source: "consultant", implemented_on: first?.implemented_on ?? "", estimated: first?.implemented_on_estimated ?? false, notes: first?.client_notes ?? "", links: (first?.evidence_links ?? []).join("\n") });
  const [verify, setVerify] = useState({ state: first?.verification ?? "unverified", how: first?.verified_how ?? "" });
  const [followNote, setFollowNote] = useState("");

  const apply = (r: { ok: true; value: Rec } | { ok: false; error: string }, done?: () => void) => {
    if (r.ok) { setRec(r.value); setF(fromRec(r.value)); setProblem(null); setSaved(true); done?.(); } else setProblem(r.error);
  };
  const save = () => start(async () => {
    if (!rec) {
      const r = await createRecAction(client.id, client.slug, toBody(f));
      if (r.ok) router.push(`${back}/${r.value.id}`); else setProblem(r.error);
    } else apply(await saveRecAction(client.id, client.slug, rec.id, rec.revision, toBody(f)));
  });
  const move = (to: RecState) => start(async () => apply(await moveRecAction(client.id, client.slug, rec!.id, to)));
  const saveProgress = () => start(async () => apply(await progressRecAction(client.id, client.slug, rec!.id, { status: prog.status, source: prog.source, implemented_on: prog.implemented_on || null, estimated: prog.estimated && !!prog.implemented_on, notes: prog.notes, links: lines(prog.links) })));
  const saveVerify = () => start(async () => apply(await verifyRecAction(client.id, client.slug, rec!.id, verify.state, verify.how)));
  const followUp = () => start(async () => apply(await followUpRecAction(client.id, client.slug, rec!.id, followNote), () => setFollowNote("")));

  return (
    <section className="max-w-4xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link href={back} className="text-sm font-semibold text-[var(--brand-teal)] hover:underline">← Recommendations</Link>
          <h1 className="mt-1 text-2xl font-bold">{rec ? "Edit brief" : "New brief"}</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{client.client_name}. Plain words a non-expert team can follow.</p>
        </div>
        {rec ? <span className={`rounded-lg px-3 py-1 text-sm font-semibold ${rec.review_state === "published" ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-900"}`}>{STATE_LABEL[rec.review_state]}{rec.review_state === "published" ? "" : ": not visible to the client"}</span> : null}
      </header>
      {problem ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{problem}</p> : null}

      <div className={`${card} space-y-4 p-5`}>
        <Field label="Title" hint="Starts with the action: “Rewrite the title of your slab leak page”."><input value={f.title} onChange={set("title")} className={input} /></Field>
        <div className="grid gap-4 sm:grid-cols-4">
          <Field label="Category"><select value={f.category} onChange={set("category")} className={input}><option value="visibility">Visibility</option><option value="traffic">Traffic</option><option value="leads">Leads</option></select></Field>
          <Field label="Helps"><select value={f.focus} onChange={set("focus")} className={input}><option value="seo">Search</option><option value="geo">AI visibility</option><option value="both">Search and AI</option></select></Field>
          <Field label="Priority"><select value={f.priority} onChange={set("priority")} className={input}><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></Field>
          <Field label="Confidence"><select value={f.confidence} onChange={set("confidence")} className={input}><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></Field>
        </div>
        <Field label="What we found" hint="What the evidence shows."><textarea value={f.finding} onChange={set("finding")} rows={3} className={input} /></Field>
        <Field label="Why it matters"><textarea value={f.explanation} onChange={set("explanation")} rows={3} className={input} /></Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Cause"><select value={f.cause_kind} onChange={set("cause_kind")} className={input}><option value="hypothesis">Hypothesis: our best explanation</option><option value="confirmed">Confirmed by two independent signals</option></select></Field>
          <div className="sm:col-span-2"><Field label="Cause, in a sentence"><input value={f.cause_text} onChange={set("cause_text")} className={input} /></Field></div>
        </div>
        <Field label="What to do" hint="One sentence."><textarea value={f.action} onChange={set("action")} rows={2} className={input} /></Field>
        <Field label="Steps" hint="One per line. These become the client's checklist."><textarea value={f.instructions} onChange={set("instructions")} rows={5} className={input} /></Field>
        <Field label="Pages affected" hint="One address per line. Checked against the live site in a later step."><textarea value={f.target_urls} onChange={set("target_urls")} rows={2} className={`${input} font-mono`} /></Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Expected impact" hint="A rough estimate, never a promise."><input value={f.expected_impact} onChange={set("expected_impact")} className={input} /></Field>
          <Field label="Effort (minutes)"><input type="number" value={f.effort_min} onChange={set("effort_min")} className={input} /></Field>
          <Field label="Who does it" hint="A role on their team."><input value={f.owner} onChange={set("owner")} className={input} /></Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-4">
          <Field label="Success metric"><input value={f.metric} onChange={set("metric")} placeholder="Click-through on this page" className={input} /></Field>
          <Field label="Today"><input value={f.metric_baseline} onChange={set("metric_baseline")} className={input} /></Field>
          <Field label="Target"><input value={f.metric_target} onChange={set("metric_target")} className={input} /></Field>
          <Field label="Days to measure"><input type="number" value={f.metric_days} onChange={set("metric_days")} placeholder="28" className={input} /></Field>
        </div>
        <Field label="Evidence" hint="One per line: what we saw | where (source and date)."><textarea value={f.evidence} onChange={set("evidence")} rows={3} className={input} /></Field>
        <Field label="Confidence: why" hint="One reason per line. Only SMA sees this."><textarea value={f.confidence_reasons} onChange={set("confidence_reasons")} rows={2} className={input} /></Field>
        <Field label={"Internal notes"} hint="Only SMA sees these. They never appear in the client portal."><textarea value={f.internal_notes} onChange={set("internal_notes")} rows={3} className={`${input} bg-amber-50`} /></Field>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={save} disabled={pending} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{pending ? <><Spinner />Saving…</> : rec ? "Save changes" : "Create draft"}</button>
          {saved ? <span className="text-sm text-green-800">Saved.</span> : null}
        </div>
      </div>

      {rec ? (
        <>
          <div className={`${card} space-y-3 p-5`}>
            <h2 className="text-lg font-bold">Review</h2>
            {rec.publish_gaps.length > 0 && rec.review_state !== "published" ? <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-900">Before it can be published it still needs: {rec.publish_gaps.join("; ")}.</p> : null}
            <div className="flex flex-wrap gap-2">
              {rec.next_states.map((s) => (
                <button key={s} type="button" disabled={pending} onClick={() => move(s)} className={`rounded-lg border px-4 py-2 text-sm font-semibold disabled:opacity-50 ${s === "published" ? "border-[var(--brand-dark)] bg-[var(--brand-dark)] text-white" : "border-[var(--border)] bg-white"}`}>
                  {s === "published" ? "Publish to client" : s === "draft" ? "Back to draft" : s === "archived" ? "Archive" : s === "under_review" ? "Send for review" : s === "approved" ? "Approve" : STATE_LABEL[s]}
                </button>
              ))}
            </div>
            <p className="text-xs text-[var(--text-secondary)]">Publishing shows this to the client only. It does not create a task for SMA.{rec.published_at ? ` Published ${rec.published_at.slice(0, 10)} by ${rec.published_by}.` : ""}</p>
          </div>

          <div className={`${card} space-y-4 p-5`}>
            <h2 className="text-lg font-bold">What the client has done</h2>
            <p className="text-xs text-[var(--text-secondary)]">Often you will only know what they tell you, or nothing. Record it with who said so. Verified and measured are filled only when there is evidence.</p>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Status"><select value={prog.status} onChange={(e) => setProg({ ...prog, status: e.target.value as typeof prog.status })} className={input}>{Object.entries(IMPL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
              <Field label="Who said so"><select value={prog.source} onChange={(e) => setProg({ ...prog, source: e.target.value })} className={input}><option value="consultant">I recorded it (from a call or email)</option><option value="client">The client reported it</option><option value="live_check">Seen on the live page</option></select></Field>
              <Field label="Date it went live"><input type="date" value={prog.implemented_on} onChange={(e) => setProg({ ...prog, implemented_on: e.target.value })} className={input} /></Field>
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={prog.estimated} onChange={(e) => setProg({ ...prog, estimated: e.target.checked })} /> That date is an estimate</label>
            <Field label="Notes"><textarea value={prog.notes} onChange={(e) => setProg({ ...prog, notes: e.target.value })} rows={2} className={input} /></Field>
            <Field label="Links or proof" hint="One per line."><textarea value={prog.links} onChange={(e) => setProg({ ...prog, links: e.target.value })} rows={2} className={`${input} font-mono`} /></Field>
            <button type="button" onClick={saveProgress} disabled={pending} className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold disabled:opacity-50">Save what they did</button>
            <div className="grid gap-4 border-t border-[var(--border)] pt-4 sm:grid-cols-3">
              <Field label="Verified"><select value={verify.state} onChange={(e) => setVerify({ ...verify, state: e.target.value as typeof verify.state })} className={input}><option value="unverified">Not verified</option><option value="verified">Verified: I saw it</option><option value="not_seen">Checked, not seen</option><option value="unreadable">Could not read the page</option></select></Field>
              <div className="sm:col-span-2"><Field label="How you know" hint="What you saw and where."><input value={verify.how} onChange={(e) => setVerify({ ...verify, how: e.target.value })} className={input} /></Field></div>
            </div>
            <button type="button" onClick={saveVerify} disabled={pending} className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold disabled:opacity-50">Save verification</button>
            <div className="flex flex-wrap items-end gap-2 border-t border-[var(--border)] pt-4">
              <div className="min-w-[16rem] flex-1"><Field label="Followed up" hint={rec.last_follow_up_on ? `Last: ${rec.last_follow_up_on}` : "Note that you chased them, even with no reply."}><input value={followNote} onChange={(e) => setFollowNote(e.target.value)} placeholder="Emailed Dana, no reply" className={input} /></Field></div>
              <button type="button" onClick={followUp} disabled={pending} className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold disabled:opacity-50">Record follow-up</button>
            </div>
          </div>

          <div className={`${card} p-5`}>
            <h2 className="text-lg font-bold">Activity</h2>
            <ul className="mt-2 divide-y divide-[var(--border)] text-sm">
              {(rec.events ?? []).map((e, i) => (
                <li key={i} className="py-2">
                  <span className="font-semibold">{e.kind === "state" ? `${STATE_LABEL[(e.from ?? "draft") as RecState]} → ${STATE_LABEL[(e.to ?? "draft") as RecState]}` : e.kind === "progress" ? `Client status: ${e.to}` : e.kind === "verified" ? `Verification: ${e.to}` : e.kind === "created" ? "Created" : e.kind === "note" ? "Follow-up" : "Edited"}</span>
                  <span className="text-[var(--text-secondary)]"> · {e.by} · {e.at.slice(0, 16).replace("T", " ")}</span>
                  {typeof e.detail?.note === "string" && e.detail.note ? <div className="text-xs text-[var(--text-secondary)]">{e.detail.note}</div> : null}
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : null}
    </section>
  );
}
