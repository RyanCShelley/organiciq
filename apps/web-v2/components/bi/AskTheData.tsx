"use client";

import { useEffect, useRef, useState } from "react";

import { askAction, askStatusAction } from "@/app/(app)/[clientSlug]/bi/actions";
import { Markdown } from "@/components/bi/Markdown";
import { Spinner } from "@/components/ui/Spinner";
import type { AskDepth, AskInfo, AskItem } from "@/lib/bi";

const DEPTH_LABEL: Record<AskDepth, { name: string; hint: string }> = {
  quick: { name: "Quick", hint: "Sonnet 5.5: most questions, about 5 cents" },
  deep: { name: "Deep dive", hint: "Opus 5.5: harder questions, about 10 cents" },
  deepest: { name: "Deepest", hint: "Fable 5.1: the hardest, about 30 cents" },
};
const EXAMPLES = [
  "Which channels bring in the most conversions?",
  "What traffic trends over the last 3 months should I be aware of?",
  "What keywords are stable or losing?",
  "What pages do users leave soonest?",
];

function Answer({ item }: { item: AskItem }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-2">
      <div className="rounded-lg bg-[var(--bg)] px-4 py-2 text-sm font-semibold">{item.question}</div>
      <div className="rounded-lg border border-[var(--border)] bg-white px-4 py-3">
        {item.status === "running" ? (
          <p className="text-sm text-[var(--text-secondary)]">
            <Spinner />
            Working it out from the data{item.queries.length ? `: ${item.queries.length} lookup${item.queries.length === 1 ? "" : "s"} so far` : ""}…
          </p>
        ) : item.status === "failed" ? (
          <p role="alert" className="text-sm font-semibold text-red-700">{item.error ?? "That question could not be answered."}</p>
        ) : (
          <Markdown text={item.answer ?? ""} />
        )}
        {item.status !== "running" ? (
          <div className="mt-2 flex flex-wrap items-center gap-3 border-t border-[var(--border)] pt-2 text-xs text-[var(--text-tertiary)]">
            <span>{DEPTH_LABEL[item.depth].name}</span>
            <span>${item.cost_usd.toFixed(2)}</span>
            {item.queries.length > 0 ? (
              <button type="button" onClick={() => setOpen((v) => !v)} className="font-semibold underline">
                {open ? "Hide" : "How this was worked out"} ({item.queries.length} lookup{item.queries.length === 1 ? "" : "s"})
              </button>
            ) : null}
          </div>
        ) : null}
        {open ? (
          <ol className="mt-2 list-decimal space-y-2 pl-5 text-xs text-[var(--text-secondary)]">
            {item.queries.map((q, i) => (
              <li key={i}>
                <code className="block whitespace-pre-wrap break-all rounded bg-[var(--bg)] p-2">{q.query}</code>
                {q.error ? <span className="text-red-700">Did not run: {q.error}</span> : <span>{q.rows} row{q.rows === 1 ? "" : "s"}</span>}
              </li>
            ))}
          </ol>
        ) : null}
      </div>
    </div>
  );
}

/**
 * A box to ask the data in plain words. The answer is worked out in the background (a question takes 15 to 60 seconds)
 * and polled for; every answer shows the lookups behind it.
 */
export function AskTheData({ clientId, info }: { clientId: string; info: AskInfo | null }) {
  const [items, setItems] = useState<AskItem[]>(() => (info ? [...info.recent].reverse() : []));
  const [question, setQuestion] = useState("");
  const [depth, setDepth] = useState<AskDepth>("quick");
  const [error, setError] = useState<string | null>(null);
  const [left, setLeft] = useState(info?.spend.left_usd ?? 0);
  const endRef = useRef<HTMLDivElement | null>(null);
  const running = items.filter((i) => i.status === "running").map((i) => i.id).join(",");

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      for (const id of running.split(",")) {
        const r = await askStatusAction(clientId, id);
        if (r.ok) {
          setItems((all) => all.map((x) => (x.id === id ? r.item : x)));
          setLeft(r.left_usd);
        }
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [running, clientId]);

  const send = async (text: string) => {
    const q = text.trim();
    if (q.length < 3) return;
    setError(null);
    const history = items
      .filter((i) => i.status === "done" && i.answer)
      .slice(-3)
      .flatMap((i) => [{ role: "user" as const, content: i.question }, { role: "assistant" as const, content: (i.answer ?? "").slice(0, 3000) }]);
    const r = await askAction(clientId, q, depth, history);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    setQuestion("");
    setItems((all) => [...all, { id: r.id, status: "running", question: q, depth, model: info?.depths[depth].model ?? "", answer: null, error: null, queries: [], cost_usd: 0, asked_by: "", created_at: null }]);
    setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }), 50);
  };

  const busy = items.some((i) => i.status === "running");
  return (
    <section className="rounded-xl border border-[var(--brand-teal)] bg-[var(--surface)] p-5">
      <h2 className="text-lg font-bold">Ask the data</h2>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        Ask in plain words. Answers come only from this client&apos;s data, with the figures, the period and where they came from. It cannot change anything.
      </p>
      {!info?.ready ? (
        <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Questions need the Anthropic key on the API service. Until it is set, this box cannot answer.</p>
      ) : (
        <>
          {items.length === 0 ? (
            <ul className="mt-3 flex flex-wrap gap-2">
              {EXAMPLES.map((e) => (
                <li key={e}>
                  <button type="button" onClick={() => send(e)} disabled={busy} className="rounded-full border border-[var(--border)] bg-white px-3 py-1 text-xs font-semibold hover:bg-[var(--bg)] disabled:opacity-50">{e}</button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-4 max-h-[36rem] space-y-4 overflow-y-auto pr-1">
              {items.map((i) => <Answer key={i.id} item={i} />)}
              <div ref={endRef} />
            </div>
          )}
          <form
            className="mt-4 flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void send(question);
            }}
          >
            <label className="min-w-[16rem] flex-1 text-xs font-semibold">
              Your question
              <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="What pages do visitors stay on the longest?" className="mt-1 block w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm font-normal" />
            </label>
            <label className="text-xs font-semibold">
              How deep
              <select value={depth} onChange={(e) => setDepth(e.target.value as AskDepth)} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-2 text-sm font-normal" title={DEPTH_LABEL[depth].hint}>
                {(Object.keys(DEPTH_LABEL) as AskDepth[]).map((d) => <option key={d} value={d}>{DEPTH_LABEL[d].name}</option>)}
              </select>
            </label>
            <button type="submit" disabled={busy || question.trim().length < 3} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
              {busy ? <><Spinner />Working…</> : "Ask"}
            </button>
          </form>
          <p className="mt-2 text-xs text-[var(--text-tertiary)]">
            {DEPTH_LABEL[depth].hint}. ${left.toFixed(2)} left for questions this month{info ? ` of $${info.spend.cap_usd.toFixed(0)}` : ""}.
          </p>
          {error ? <p role="alert" className="mt-2 text-sm font-semibold text-red-700">{error}</p> : null}
        </>
      )}
    </section>
  );
}
