"use client";
import { useState, useTransition } from "react";
import { saveWatchTargetAction } from "@/app/(app)/[clientSlug]/decision-engine/actions";

export type WatchItem = {
  kind: "keyword" | "prompt"; item_key?: string; text: string; provider: string | null;
  state: string; target_url: string | null; priority: boolean; note: string | null;
  observation: { observed_on?: string; brand_mentioned?: boolean; brand_cited?: boolean; citation_url?: string; source?: string; answer?: string };
};
const input = "w-full rounded-md border border-[var(--border)] bg-[var(--surface)] p-2 text-sm";
const blank: WatchItem = { kind: "prompt", text: "", provider: "", state: "unmapped", target_url: null, priority: false, note: null, observation: {} };

export function WatchlistPanel({ initial, clientId, slug }: { initial: WatchItem[]; clientId: string; slug: string }) {
  const [rows, setRows] = useState(initial);
  const [editing, setEditing] = useState<WatchItem | null>(null);
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const save = () => startTransition(async () => {
    if (!editing) return;
    const result = await saveWatchTargetAction(clientId, slug, editing);
    if (result.ok) { setRows(result.rows); setEditing(null); setMessage("Target saved. Rerun the assessment to include new prompt evidence in its findings."); }
    else setMessage(result.error);
  });
  const patch = (values: Partial<WatchItem>) => setEditing(x => x ? { ...x, ...values } : x);
  const observe = (values: Partial<WatchItem["observation"]>) => editing && patch({ observation: { ...editing.observation, ...values } });
  return <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 space-y-3">
    <h2 className="text-xl font-bold">Keyword and prompt targets</h2>
    <p className="text-sm">{rows.length} selected items · {rows.filter(x => x.state === "unmapped").length} need mapping. Target ownership is your decision; observed rankings and citations are evidence.</p>
    <button className="rounded-md border px-3 py-2 text-sm" onClick={() => { setEditing({ ...blank, observation: {} }); setMessage(null); }}>Add keyword or prompt</button>
    {editing && <div className="space-y-3 rounded-lg border border-[var(--border)] p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">Item type<select className={input} value={editing.kind} disabled={Boolean(editing.item_key)} onChange={e => patch({ kind: e.target.value as WatchItem["kind"] })}><option value="keyword">Keyword</option><option value="prompt">Prompt</option></select></label>
        <label className="text-sm">Provider / model<input className={input} value={editing.provider ?? ""} disabled={Boolean(editing.item_key)} onChange={e => patch({ provider: e.target.value })} /></label>
      </div>
      <label className="block text-sm">Exact keyword or prompt<textarea className={input} value={editing.text} disabled={Boolean(editing.item_key)} onChange={e => patch({ text: e.target.value })} /></label>
      <label className="block text-sm">Target state<select className={input} value={editing.state} onChange={e => patch({ state: e.target.value })}><option value="unmapped">Needs mapping</option><option value="existing">Existing page</option><option value="planned">Planned page</option><option value="excluded">Intentionally excluded</option></select></label>
      {editing.state === "existing" && <label className="block text-sm">Target page<input className={input} value={editing.target_url ?? ""} onChange={e => patch({ target_url: e.target.value })} /></label>}
      <label className="block text-sm"><input type="checkbox" checked={editing.priority} onChange={e => patch({ priority: e.target.checked })} /> Strategic priority</label>
      <label className="block text-sm">Planned page description or decision note<textarea className={input} value={editing.note ?? ""} onChange={e => patch({ note: e.target.value })} /></label>
      {editing.kind === "prompt" && <details><summary className="cursor-pointer text-sm font-semibold">Record an observed prompt response</summary>
        <p className="my-2 text-sm">Enter actual observations from your tester. Unknown and negative results are different. No external prompt run is started here.</p>
        <label className="block text-sm">Observation date<input type="date" className={input} value={editing.observation.observed_on ?? ""} onChange={e => observe({ observed_on: e.target.value || undefined })} /></label>
        {(["brand_mentioned", "brand_cited"] as const).map(field => <label className="block text-sm" key={field}>{field === "brand_mentioned" ? "Brand mentioned" : "Client domain cited"}<select className={input} value={editing.observation[field] === undefined ? "unknown" : String(editing.observation[field])} onChange={e => observe({ [field]: e.target.value === "unknown" ? undefined : e.target.value === "true" })}><option value="unknown">Unknown</option><option value="true">Yes</option><option value="false">No</option></select></label>)}
        <label className="block text-sm">Observed citation URL<input className={input} value={editing.observation.citation_url ?? ""} onChange={e => observe({ citation_url: e.target.value })} /></label>
        <label className="block text-sm">Response / evidence<textarea className={input} rows={4} value={editing.observation.answer ?? ""} onChange={e => observe({ answer: e.target.value, source: "Manual observation" })} /></label>
      </details>}
      <button disabled={pending} className="rounded-md border px-3 py-2 text-sm" onClick={save}>Save target</button>{" "}
      <button disabled={pending} className="rounded-md border px-3 py-2 text-sm" onClick={() => setEditing(null)}>Cancel</button>
    </div>}
    {message && <p className="text-sm" role="status">{message}</p>}
    <details><summary className="cursor-pointer font-semibold">Review all targets</summary>
      <label className="mt-3 block text-sm">Filter targets<input className={input} value={filter} onChange={e => setFilter(e.target.value)} /></label>
      <ul className="max-h-[32rem] overflow-auto">{rows.filter(x => x.text.toLowerCase().includes(filter.toLowerCase())).map(x => <li key={`${x.kind}-${x.item_key}`} className="border-t border-[var(--border)] py-3 text-sm">
        <div className="flex justify-between gap-3"><p><strong>{x.kind === "prompt" ? "Prompt" : "Keyword"}{x.priority ? " · priority" : ""}</strong> · {x.text}</p><button className="shrink-0 underline" onClick={() => { setEditing(structuredClone(x)); setMessage(null); }}>Review target</button></div>
        <p>{x.state === "unmapped" ? "Needs mapping" : x.state} · {x.target_url ?? x.note ?? "No page selected"}{x.provider ? ` · ${x.provider}` : ""}</p>
        {x.observation.observed_on && <p>Observed {x.observation.observed_on} · mention: {x.observation.brand_mentioned === undefined ? "unknown" : x.observation.brand_mentioned ? "yes" : "no"} · citation: {x.observation.brand_cited === undefined ? "unknown" : x.observation.brand_cited ? "yes" : "no"}{x.observation.citation_url ? ` · ${x.observation.citation_url}` : ""}</p>}
      </li>)}</ul>
    </details>
  </section>;
}
