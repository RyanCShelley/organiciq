"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { savePlanReviewAction } from "@/app/(app)/[clientSlug]/decision-engine/actions";
import { ACTION_FAMILIES, actionCount, selectedAction, toggleAction, type Brief, type PlanReview } from "@/lib/plan-review";
import { usePlanState } from "./PlanReviewState";

const inputClass = "w-full rounded-md border border-[var(--border)] bg-[var(--surface)] p-2 text-sm";
const buttonClass = "rounded-md border border-[var(--border)] px-3 py-2 text-sm disabled:opacity-50";

export function PlanReviewPanel({ initial, clientId, slug, month, lockedUids = [] }: {
  initial: PlanReview; clientId: string; slug: string; month: string; lockedUids?: string[];
}) {
  const [stage, setStage] = useState(1);
  const [family, setFamily] = useState(initial.proposals.find(item => item.branch === initial.focus)?.family ?? initial.proposals[0]?.family ?? "priority_page");
  const [review, setReview] = useState(initial);
  const [dirty, setDirty] = useState(false);
  const planState = usePlanState();
  const [changedUid, setChangedUid] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  const update = (patch: Partial<PlanReview>) => { setReview(r => ({ ...r, ...patch })); setDirty(true); planState.setDirty(true); setMessage(null); };
  const edit = (index: number, patch: Partial<Brief>) => update({ items: review.items.map((item, i) => i === index ? { ...item, ...patch } : item) });
  const select = (group: Brief, step: string, index: number) => {
    const current = selectedAction(review.items, group, step);
    if (current && lockedUids.includes(current.action_uid)) return;
    const items = toggleAction(review.items, group, step, index, lockedUids);
    update({ items });
    setChangedUid(null);
    setMessage(`${actionCount(items)} actions selected. Your checkboxes are the plan; approve when ready.`);
  };
  const add = (item: Brief) => { update({ items: [...review.items, item] }); setChangedUid(item.action_uid); setStage(3); };
  const manual = () => add({
    action_uid: `manual-${crypto.randomUUID()}`, id: "MANUAL", family: "investigation",
    title: "Investigate a material change", branch: "visibility", target_url: "", term: null,
    why: "", done_when: "", steps: [""], evidence: [], finding_ids: [], effort_min: 60,
    metric: "Documented finding and next decision", metric_key: "decision", check_after_days: 28,
  });
  const save = (approve: boolean) => startTransition(async () => {
    setMessage(null);
    const result = await savePlanReviewAction(clientId, slug, month, review, approve);
    if (result.ok) {
      setReview(result.review); setDirty(false); planState.setDirty(false);
      setMessage(result.warning ?? (approve ? "Plan approved. The saved version is ready for assignment and delivery." : "Draft saved."));
      router.refresh();
    } else setMessage(result.error);
  });
  const move = (index: number, delta: number) => {
    const items = [...review.items];
    [items[index], items[index + delta]] = [items[index + delta], items[index]];
    update({ items });
  };

  return <section className="space-y-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6" aria-labelledby="review-heading">
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <h2 id="review-heading" className="text-xl font-bold">Choose this month’s work</h2>
      <p className="text-sm">{actionCount(review.items)} / {review.capacity} actions · {dirty ? "Unsaved changes" : review.approved_at ? `Approved version ${review.revision}` : "Draft"}</p>
    </div>
    <nav aria-label="Monthly review steps" className="flex flex-wrap gap-2">{["Set direction", "Choose actions", "Review & approve"].map((label, index) => <button key={label} className={`${buttonClass} ${stage === index + 1 ? "bg-[var(--brand-teal-deep)] text-white" : ""}`} aria-current={stage === index + 1 ? "step" : undefined} onClick={() => setStage(index + 1)}>{index + 1}. {label}</button>)}</nav>
    {review.page_evidence_note && <p className="text-xs text-[var(--text-secondary)]">{review.page_evidence_note}</p>}
    {message && <p role="status" className="rounded-lg border border-[var(--brand-teal-deep)] bg-[var(--surface-muted)] p-3 text-sm">{message}</p>}
    {stage === 1 && <div className="space-y-4">
    <p className="text-sm text-[var(--text-secondary)]">After reviewing last month and speaking with the client, decide where this month’s work should focus.</p>
    <label className="block max-w-md text-sm font-semibold">This month’s focus
      <select className={inputClass} value={review.focus} onChange={e => update({ focus: e.target.value })}>
        <option value="">Choose after reviewing</option>
        <option value="visibility">Visibility</option><option value="traffic">Traffic</option><option value="leads">Leads</option>
        <option value="continue_strategy">Continue current strategy</option><option value="insufficient_evidence">Insufficient evidence</option>
      </select>
    </label>
    <details open={Boolean(review.strategy || review.reason)}><summary className="cursor-pointer text-sm">Client context and priorities (optional)</summary>
      <label className="mt-2 block text-sm">Client strategy and current priorities<textarea className={inputClass} rows={2} value={review.strategy} onChange={e => update({ strategy: e.target.value })} /></label>
      <label className="mt-2 block text-sm">Decision note (optional)<textarea className={inputClass} rows={2} value={review.reason} onChange={e => update({ reason: e.target.value })} /></label>
    </details>
    <button className={`${buttonClass} bg-[var(--brand-teal-deep)] text-white`} onClick={() => setStage(2)}>Choose actions →</button>
    </div>}
    {stage === 2 && <div className="border-t border-[var(--border)] pt-4">
      <h3 className="font-semibold">What type of improvement do you want to make?</h3>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">Choose an action type to review its opportunities. Check individual tasks to add them to this month’s plan.</p>
      <div className="my-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(ACTION_FAMILIES).map(([key, label]) => {
        const count = review.proposals.filter(item => item.family === key).length;
        if (!count) return null;
        return <button key={key} onClick={() => setFamily(key)} aria-pressed={family === key} className={`rounded-lg border p-3 text-left text-sm ${family === key ? "border-[var(--brand-teal-deep)] bg-[var(--surface-muted)] font-semibold" : "border-[var(--border)]"}`}>{label}<span className="mt-1 block text-xs font-normal text-[var(--text-secondary)]">{count} page {count === 1 ? "opportunity" : "opportunities"}</span></button>;
      })}</div>
      {review.proposals.filter(group => group.family === family).map(group => <article key={group.action_uid} className="mt-3 rounded-lg border border-[var(--border)] p-4">
        <h4 className="text-sm font-semibold">{ACTION_FAMILIES[group.family]}</h4>
        <p className="break-all text-sm">{group.target_url}</p>

        <div className="mt-3 space-y-3">{group.steps.map((step, index) => {
          const selected = selectedAction(review.items, group, step);
          const locked = selected && lockedUids.includes(selected.action_uid);
          return <label key={index} className="flex cursor-pointer items-start gap-3 rounded-md bg-[var(--surface-muted)] p-3 text-sm">
            <input type="checkbox" className="mt-1" checked={Boolean(selected)} disabled={pending || Boolean(locked)} onChange={() => select(group, step, index)} />
            <span>{step}{locked && <span className="block text-xs">Assigned or delivered · protected from scope changes</span>}</span>
          </label>;
        })}</div>
        <details className="mt-3 text-sm"><summary className="cursor-pointer">Why this is recommended</summary>
          <p className="mt-2">{group.why}</p>
          <p className="mt-2">Outcome to check: {group.metric}</p>
          <ul className="mt-2 list-disc space-y-1 pl-5">{group.evidence.filter(Boolean).map((line, i) => <li key={i}>{line}</li>)}</ul>
        </details>
      </article>)}
      {!!review.recommendation_limits?.length && <details className="mt-3 text-sm"><summary className="cursor-pointer">Work withheld from new recommendations ({review.recommendation_limits.length})</summary><ul className="mt-2 space-y-2">{review.recommendation_limits.map((item, i) => <li key={i}><strong>{item.title}</strong><p className="break-all">{item.target_url}</p><p>{item.reason}</p></li>)}</ul></details>}
      {review.proposals.length === 0 && <p className="mt-2 text-sm">No supported recommendations in this run. You can add a custom action below.</p>}
      <div className="mt-4 flex flex-wrap gap-2"><button className={buttonClass} onClick={manual}>Add a custom action</button><button className={`${buttonClass} bg-[var(--brand-teal-deep)] text-white`} onClick={() => setStage(3)}>Review {actionCount(review.items)} selected actions →</button></div>
    </div>}
    {stage === 3 && <div className="space-y-4">
    <h3 id="selected-plan" className="scroll-mt-6 border-t border-[var(--border)] pt-4 font-semibold">Selected work · {actionCount(review.items)} actions</h3>
    <p className="text-sm text-[var(--text-secondary)]">This is a summary of the actions checked above. Reorder work if needed; approval accepts this selection.</p>
    {review.items.length === 0 && <p className="text-sm">No actions selected yet. Add a recommendation above or use “Add custom action.”</p>}
    {review.items.map((item, index) => <details open={changedUid === item.action_uid} key={item.action_uid} className={`rounded-lg border p-4 ${changedUid === item.action_uid ? "border-[var(--brand-teal-deep)] bg-[var(--surface-muted)]" : "border-[var(--border)]"}`}>
      <summary className="cursor-pointer font-semibold">{index + 1}. {item.title}{item.steps.length > 1 ? ` · ${item.steps.length} actions in a previously saved bundle` : ""}</summary>
      <div className="mt-3 space-y-3">
        <div className="flex flex-wrap gap-2">
          <button className={buttonClass} disabled={index === 0 || pending} onClick={() => move(index, -1)}>Move up</button>
          <button className={buttonClass} disabled={index === review.items.length - 1 || pending} onClick={() => move(index, 1)}>Move down</button>
          <button className={buttonClass} disabled={pending || lockedUids.includes(item.action_uid)} onClick={() => update({ items: review.items.filter((_, i) => i !== index) })}>Remove</button>
        </div>
        {changedUid === item.action_uid && <p className="text-sm font-semibold">Updated in this draft · {item.steps.length} steps · {item.evidence.length} evidence lines</p>}
        <p className="break-all text-sm">{item.target_url || "Choose a target page in Edit action details."}</p>
        <p className="whitespace-pre-line text-sm">{item.why}</p>
        <ol className="list-decimal space-y-1 pl-5 text-sm">{item.steps.map((step, i) => <li key={i}>{step}</li>)}</ol>
        <p className="whitespace-pre-line text-sm"><strong>Done when:</strong> {item.done_when}</p>
        <p className="text-sm"><strong>Primary outcome:</strong> {item.metric} · check {item.check_after_days} days after shipment</p>
        <details className="text-sm"><summary className="cursor-pointer">Evidence ({item.evidence.length})</summary><ul className="mt-2 list-disc pl-5">{item.evidence.map((line, i) => <li key={i}>{line}</li>)}</ul></details>
        <details><summary className="cursor-pointer text-sm font-semibold">Edit action details (optional)</summary><div className="mt-3 space-y-3">
        <label className="block text-sm">Action type<select className={inputClass} value={item.family} onChange={e => edit(index, { family: e.target.value })}>{Object.entries(ACTION_FAMILIES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">Brief title<input className={inputClass} value={item.title} onChange={e => edit(index, { title: e.target.value })} /></label>
          <label className="block text-sm">Target page<input className={inputClass} value={item.target_url} onChange={e => edit(index, { target_url: e.target.value })} placeholder="https://example.com/page" /></label>
        </div>
        <label className="block text-sm">Why this work<textarea className={inputClass} rows={2} value={item.why} onChange={e => edit(index, { why: e.target.value })} /></label>
        <label className="block text-sm">Checklist, one step per line<textarea className={inputClass} rows={4} value={item.steps.join("\n")} onChange={e => edit(index, { steps: e.target.value.split("\n") })} /></label>
        <label className="block text-sm">Done when<textarea className={inputClass} rows={2} value={item.done_when} onChange={e => edit(index, { done_when: e.target.value })} /></label>
        <label className="block text-sm">Evidence and limitations, one per line<textarea className={inputClass} rows={3} value={item.evidence.join("\n")} onChange={e => edit(index, { evidence: e.target.value.split("\n").filter(Boolean) })} /></label>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block text-sm">Outcome to check<input className={inputClass} value={item.metric} onChange={e => edit(index, { metric: e.target.value })} /></label>
          <label className="block text-sm">Automated measurement<select className={inputClass} value={item.metric_key} onChange={e => edit(index, { metric_key: e.target.value })}>
            <option value="decision">Manual verification</option><option value="term_position">Term position</option><option value="page_clicks">Page clicks</option><option value="page_impressions">Page impressions</option><option value="page_position">Page position</option><option value="engagement_rate">Engagement rate</option><option value="page_lead_rate">Page-local lead event rate</option><option value="ai_presence">Site AI presence</option>
          </select></label>
          <label className="block text-sm">Days after shipment<input type="number" min={7} max={180} className={inputClass} value={item.check_after_days} onChange={e => edit(index, { check_after_days: Number(e.target.value) })} /></label>
        </div>
        </div></details>
      </div>
    </details>)}
    <button className={buttonClass} disabled={pending} onClick={() => setStage(2)}>← Change selected actions</button>

    {review.setup_findings.length > 0 && <details><summary className="cursor-pointer font-semibold">Page ownership to review · no growth slot used</summary>{review.setup_findings.map((x, i) => <p className="mt-2 text-sm" key={i}>{x.target_url}: {x.why}</p>)}</details>}
    <h3 className="border-t border-[var(--border)] pt-4 font-semibold">3. Approve the selected actions</h3>
    <p className="text-sm">Approval makes this saved selection available for assignment below. Changes after approval create a draft and require approval again.</p>
    {actionCount(review.items) > review.capacity && <p role="alert" className="text-sm text-red-700">{actionCount(review.items)} actions selected; this plan allows {review.capacity}. Uncheck actions before approving.</p>}
    <div className="flex flex-wrap gap-3">
      <button className={buttonClass} disabled={pending || (!dirty && Boolean(review.approved_at))} onClick={() => save(false)}>Save draft</button>
      <button className={`${buttonClass} bg-[var(--brand-teal-deep)] text-white`} disabled={pending || actionCount(review.items) > review.capacity || (!dirty && Boolean(review.approved_at))} onClick={() => save(true)}>Approve {actionCount(review.items)} actions</button>
    </div>
    </div>}
    {review.versions.length > 0 && <details><summary className="cursor-pointer text-sm">Approved history ({review.versions.length})</summary>{review.versions.map(v => <p className="mt-1 text-sm" key={v.revision}>Version {v.revision} · {v.approved_at} · {v.approved_by}</p>)}</details>}
  </section>;
}
