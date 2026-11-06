"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, useTransition } from "react";

import { optimizerDraftAction, optimizerPageAction } from "@/app/(app)/[clientSlug]/content-optimizer/actions";
import { AskModel, card, num, shortPage } from "@/components/content/parts";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import type { ContentDepthChoice } from "@/lib/content";
import type { OptDraft, OptKind, OptPage, OptQueue } from "@/lib/optimizer";

function Copy({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" onClick={() => navigator.clipboard.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500); })} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1 text-xs font-semibold">
      {done ? "Copied" : label}
    </button>
  );
}

function Result({ d }: { d: OptDraft }) {
  if (d.kind === "opening")
    return (
      <div className="space-y-3 text-sm">
        {d.diagnosis ? <p className="text-[var(--text-secondary)]">{d.diagnosis}</p> : null}
        <div><div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">The opening now</div><p className="mt-1 rounded-lg bg-[var(--bg)] p-3">{d.before || "No opening paragraph found."}</p></div>
        {(d.options ?? []).map((o, i) => (
          <div key={i} className="rounded-lg border border-[var(--border)] p-3">
            <div className="flex items-center justify-between gap-2"><span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">Option {i + 1}</span><Copy text={o.text} /></div>
            <p className="mt-1">{o.text}</p>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">{o.why}{o.serves.length ? ` Serves: ${o.serves.join(", ")}.` : ""}</p>
          </div>
        ))}
      </div>
    );
  if (d.kind === "terms")
    return (
      <div className="space-y-3 text-sm">
        {(d.edits ?? []).map((e, i) => (
          <div key={i} className="rounded-lg border border-[var(--border)] p-3">
            <div className="flex items-center justify-between gap-2"><span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">Edit {i + 1}{e.terms.length ? ` · ${e.terms.join(", ")}` : ""}</span><Copy text={e.after} /></div>
            <p className="mt-2 text-[var(--text-secondary)] line-through">{e.before}</p>
            <p className="mt-1 font-medium">{e.after}</p>
            {e.why ? <p className="mt-2 text-xs text-[var(--text-secondary)]">{e.why}</p> : null}
          </div>
        ))}
        {(d.left_out ?? []).length ? <p className="text-xs text-[var(--text-secondary)]">Left out: {d.left_out!.join(" · ")}</p> : null}
      </div>
    );
  return (
    <div className="space-y-3 text-sm">
      {d.already_has_faq ? <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-900">The page already has an FAQ, so these are questions it does not answer yet.</p> : null}
      {(d.items ?? []).map((it, i) => (
        <div key={i} className="rounded-lg border border-[var(--border)] p-3">
          <div className="font-semibold">{it.question}</div>
          <p className="mt-1">{it.answer}</p>
          {it.from_search ? <p className="mt-1 text-xs text-[var(--text-tertiary)]">From the search “{it.from_search}”</p> : null}
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <Copy label="Copy the questions and answers" text={(d.items ?? []).map((i) => `${i.question}\n${i.answer}`).join("\n\n")} />
        {d.markup ? <Copy label="Copy the FAQ markup" text={`<script type="application/ld+json">\n${d.markup}\n</script>`} /> : null}
      </div>
      {d.markup ? <p className="text-xs text-[var(--text-secondary)]">The markup is built from these same questions and answers. Put the text on the page and the markup in its head, together: markup for questions a visitor cannot see is not allowed.</p> : null}
    </div>
  );
}

function PagePanel({ client, url, kind, onKind, queueKinds }: { client: Client; url: string; kind: OptKind; onKind: (k: OptKind) => void; queueKinds: OptQueue["kinds"] }) {
  const [page, setPage] = useState<OptPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [depth, setDepth] = useState<ContentDepthChoice>("quick");
  const [pending, start] = useTransition();
  const load = useCallback(async () => {
    const r = await optimizerPageAction(client.id, url);
    if (r.ok) { setPage(r.value); setError(null); } else setError(r.error);
  }, [client.id, url]);
  useEffect(() => { setPage(null); load(); }, [load]);
  const draft = page?.drafts[kind] ?? null;
  const running = draft?.status === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [running, load]);
  const write = () => start(async () => { const r = await optimizerDraftAction(client.id, url, kind, depth); if (r.ok) await load(); else setError(r.error); });
  return (
    <section className={`${card} space-y-4 p-5`}>
      <div>
        <h2 className="break-all text-lg font-bold">{shortPage(url)}</h2>
        {page?.title ? <p className="text-xs text-[var(--text-tertiary)]">{page.title}</p> : null}
      </div>
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      {!page && !error ? <p className="text-sm text-[var(--text-secondary)]"><Spinner />Reading the page…</p> : null}
      {page ? (
        <>
          <div role="tablist" className="flex flex-wrap gap-2">
            {(Object.keys(queueKinds) as OptKind[]).map((k) => (
              <button key={k} type="button" role="tab" aria-selected={k === kind} onClick={() => onKind(k)} className={`rounded-full border px-3 py-1 text-sm font-semibold ${k === kind ? "border-[var(--brand-dark)] bg-[var(--brand-dark)] text-white" : "border-[var(--border)] bg-white"}`}>
                {queueKinds[k].label}
              </button>
            ))}
          </div>
          <p className="text-sm text-[var(--text-secondary)]">{queueKinds[kind].does} It works from the {num(page.searches_total)} {page.searches_total === 1 ? "search" : "searches"} this page earns in the last 90 days (Search Console) and the page&apos;s own words. Nothing is sent to the site.</p>
          <AskModel ready={page.model_ready} depth={depth} onDepth={setDepth} busy={pending || running} again={draft?.status === "done"} label={queueKinds[kind].label} onRun={write} />
          {draft?.status === "failed" ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{draft.error}</p> : null}
          {draft?.status === "done" ? <Result d={draft} /> : null}
          <details className="text-sm">
            <summary className="cursor-pointer font-semibold">The searches it works from</summary>
            <ul className="mt-2 divide-y divide-[var(--border)]">
              {page.searches.map((s) => <li key={s.query} className="flex justify-between gap-3 py-1"><span>{s.query}</span><span className="tabular-nums text-[var(--text-secondary)]">position {s.position} · {num(s.impressions)} impressions · {s.clicks} clicks</span></li>)}
            </ul>
          </details>
        </>
      ) : null}
    </section>
  );
}

export function ContentOptimizer({ client, data, error }: { client: Client; data: OptQueue | null; error: string | null }) {
  const params = useSearchParams();
  const [url, setUrl] = useState<string | null>(params.get("page"));
  const [kind, setKind] = useState<OptKind>((["opening", "terms", "faq"] as const).find((k) => k === params.get("kind")) ?? "opening");
  const [typed, setTyped] = useState(params.get("page") ?? "");
  const kinds = data?.kinds ?? { opening: { label: "Rewrite the opening", does: "" }, terms: { label: "Work in these terms", does: "" }, faq: { label: "Write the FAQ", does: "" } };
  return (
    <section className="max-w-4xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Content optimizer</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">Small changes to a page that do not need a full refresh: a new opening, terms worked in where they read naturally, an FAQ. Each is written from the searches the page earns and its own words.</p>
      </header>
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      <form className="flex flex-wrap gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); if (typed.trim()) setUrl(typed.trim()); }}>
        <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="The page's full address" aria-label="Page address" className="min-w-[20rem] flex-1 rounded-lg border border-[var(--border)] bg-white px-3 py-2" />
        <button type="submit" className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 font-semibold">Open</button>
      </form>
      {url ? <PagePanel key={url} client={client} url={url} kind={kind} onKind={setKind} queueKinds={kinds} /> : null}
      {data ? (
        <section className={`${card} p-5`}>
          <h2 className="text-lg font-bold">From this month&apos;s plan</h2>
          {data.queue.length === 0 ? <p className="mt-2 text-sm text-[var(--text-secondary)]">No approved action has a part this tool does. Open a page above to use it on its own.</p> : (
            <ul className="mt-2 divide-y divide-[var(--border)] text-sm">
              {data.queue.map((q) => (
                <li key={`${q.task_id}-${q.part_id}`} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span><span className="font-semibold">{q.part_name}</span> <span className="text-[var(--text-secondary)]">· {shortPage(q.page)}</span></span>
                  <button type="button" onClick={() => { setUrl(q.page); setTyped(q.page); setKind(q.kind); }} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1 text-xs font-semibold text-[var(--brand-teal)]">{kinds[q.kind].label}</button>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
    </section>
  );
}
