"use client";

import { useEffect, useMemo, useState, useTransition } from "react";

import { buildGrowthActionAction, confirmTaskAction, topicForAction } from "@/app/(app)/[clientSlug]/engine/actions";
import type { CandidateTopic, EngineTask, GrowthActionBundle, GrowthPart, TaskDraft } from "@/lib/engine";

const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString());
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";

type Choice = { on: boolean; editing: boolean; text: string };

/** The task as the person left it: only the ticked parts, with their steps as edited. */
function assemble(bundle: Extract<GrowthActionBundle, { ok: true }>, parts: GrowthPart[], choices: Record<string, Choice>): TaskDraft {
  const chosen = parts.filter((p) => choices[p.id]?.on);
  const steps: string[] = [];
  chosen.forEach((p, i) => {
    steps.push(`# ${i + 1}. ${p.name}`);
    steps.push(...choices[p.id].text.split("\n").map((l) => l.trim()).filter(Boolean));
  });
  const evidence = [bundle.draft.evidence[0], ...chosen.flatMap((p) => p.evidence.map((e) => `${p.id}: ${e}`))].filter(Boolean);
  return {
    ...bundle.draft,
    why: `This page gets the most impressions for “${bundle.keyword}” (${bundle.chosen.impressions.toLocaleString()} over three months). The work is ${chosen.length} part${chosen.length === 1 ? "" : "s"}, done together on this one page: ${chosen.map((p) => p.name.toLowerCase()).join(", ")}.`,
    steps,
    evidence,
  };
}

/**
 * Plan a growth action from a diagnosed candidate. The candidate's topic is worked out, the best page for it is
 * shown beside the candidate's own, and everything worth doing to the chosen page appears once, here: tick what
 * to keep, edit the steps, confirm. This replaces separate lists of rules and single suggestions.
 */
export function GrowthActionPlanner({
  clientId,
  month,
  search,
  page,
  focus,
  tasks,
  onConfirmed,
}: {
  clientId: string;
  month: string;
  search: string;
  page: string;
  focus: "visibility" | "traffic" | "leads";
  tasks: EngineTask[];
  onConfirmed: (task: EngineTask) => void;
}) {
  const [topic, setTopic] = useState<CandidateTopic | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [bundle, setBundle] = useState<GrowthActionBundle | null>(null);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [showPages, setShowPages] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [pending, start] = useTransition();

  useEffect(() => {
    let live = true;
    topicForAction(clientId, search, page).then((r) => {
      if (!live) return;
      if (r.ok) {
        setTopic(r.value);
        setChosen(r.value.pages?.recommended ?? null);
      } else setError(r.error);
    });
    return () => {
      live = false;
    };
  }, [clientId, search, page]);

  // Build for the chosen page as soon as it is known, and again when another page is chosen.
  useEffect(() => {
    if (!topic?.keyword || !chosen) return;
    let live = true;
    setBuilding(true);
    setBundle(null);
    setError(null);
    buildGrowthActionAction(clientId, topic.keyword, chosen, focus, page).then((r) => {
      if (!live) return;
      setBuilding(false);
      setBundle(r);
      if (r.ok) {
        const next: Record<string, Choice> = {};
        r.parts.forEach((p) => (next[p.id] = { on: true, editing: false, text: p.steps.join("\n") }));
        r.optional.forEach((p) => (next[p.id] = { on: false, editing: false, text: p.steps.join("\n") }));
        setChoices(next);
      } else setError(r.error);
    });
    return () => {
      live = false;
    };
  }, [clientId, topic, chosen, focus, page]);

  const inPlan = (url: string) => tasks.find((t) => t.kind === "growth_action" && t.page === url && t.status !== "dropped");
  const pages = topic?.pages;
  const all = useMemo(() => (bundle && bundle.ok ? [...bundle.parts, ...bundle.optional] : []), [bundle]);
  const kept = all.filter((p) => choices[p.id]?.on).length;

  const confirm = () =>
    start(async () => {
      if (!bundle || !bundle.ok) return;
      const r = await confirmTaskAction(clientId, month, assemble(bundle, all, choices));
      if (r.ok) onConfirmed(r.value);
      else setError(r.error);
    });
  const set = (id: string, patch: Partial<Choice>) => setChoices((c) => ({ ...c, [id]: { ...c[id], ...patch } }));

  // A plain function, not a component: a component defined here would remount on every keystroke and drop the textarea's focus.
  function renderPart(p: GrowthPart, index: number | null) {
    const c = choices[p.id];
    if (!c) return null;
    return (
      <li key={p.id} className={`rounded-lg p-3 ${c.on ? "bg-[var(--bg)]" : "border border-dashed border-[var(--border)]"}`}>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <label className="flex items-start gap-2 font-semibold">
            <input type="checkbox" checked={c.on} onChange={(e) => set(p.id, { on: e.target.checked })} className="mt-1" />
            <span>
              {index != null && c.on ? `${index}. ` : ""}
              {p.name}
              <span className="ml-2 text-xs font-normal text-[var(--text-tertiary)]">
                {p.id}
                {p.core ? "" : " · extra"}
                {p.confirmed_by_rule ? " · rule" : " · unconfirmed"}
              </span>
            </span>
          </label>
          {c.on ? (
            <button type="button" onClick={() => set(p.id, { editing: !c.editing })} className="text-xs font-semibold underline">
              {c.editing ? "Done editing" : "Edit steps"}
            </button>
          ) : null}
        </div>
        {p.why ? <p className="mt-1 text-[var(--text-secondary)]">{p.why}</p> : null}
        {c.editing ? (
          <textarea
            value={c.text}
            onChange={(e) => set(p.id, { text: e.target.value })}
            rows={Math.min(14, Math.max(4, c.text.split("\n").length + 1))}
            className="mt-2 w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm"
            aria-label={`Steps for ${p.name}`}
          />
        ) : (
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[var(--text-secondary)]">
            {c.text.split("\n").filter(Boolean).map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        )}
        {p.evidence.length > 0 && !c.editing ? (
          <ul className="mt-2 list-disc pl-5 text-xs text-[var(--text-tertiary)]">
            {p.evidence.slice(0, 4).map((e) => (
              <li key={e}>{e}</li>
            ))}
            {p.evidence.length > 4 ? <li>and {p.evidence.length - 4} more</li> : null}
          </ul>
        ) : null}
      </li>
    );
  }

  let number = 0;
  return (
    <div className="mt-4 rounded-lg border border-[var(--brand-teal)] p-4 text-sm">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--brand-teal)]">Growth action</h4>
      {!topic && !error ? <p className="mt-2 text-[var(--text-secondary)]">Finding the best page for this topic…</p> : null}
      {topic && !topic.keyword ? <p className="mt-2 text-[var(--text-secondary)]">{topic.source}, so there is no topic to plan around.</p> : null}

      {topic?.keyword && pages ? (
        <div className="mt-2 text-[var(--text-secondary)]">
          Topic: <strong>{topic.keyword}</strong> <span className="text-xs text-[var(--text-tertiary)]">({topic.source})</span>.{" "}
          {pages.recommended === page
            ? "This page is the best one for the topic."
            : pages.recommended
              ? `The best page for it is ${shortPage(pages.recommended)}, not this one.`
              : "No page shows for it."}{" "}
          {pages.pages.length > 1 ? (
            <button type="button" onClick={() => setShowPages((v) => !v)} className="text-xs font-semibold underline">
              {showPages ? "Hide the pages" : `Choose a different page (${pages.pages.length})`}
            </button>
          ) : null}
          {showPages ? (
            <>
              <p className="mt-1 text-xs text-[var(--text-tertiary)]">{pages.rule}</p>
              <ul className="mt-2 divide-y divide-[var(--border)]">
                {pages.pages.slice(0, 6).map((p) => (
                  <li key={p.url} className="flex flex-wrap items-center gap-3 py-1.5">
                    <input type="radio" name={`pick-${search}-${page}`} checked={chosen === p.url} onChange={() => setChosen(p.url)} aria-label={`Work on ${shortPage(p.url)}`} />
                    <span className="min-w-0 flex-1 break-all font-medium">{shortPage(p.url)}</span>
                    {p.url === pages.recommended ? <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs font-semibold text-green-800">best page</span> : null}
                    {p.url === page ? <span className="rounded bg-[var(--bg)] px-1.5 py-0.5 text-xs font-semibold">this candidate</span> : null}
                    {inPlan(p.url) ? <span className="text-xs font-semibold text-green-800">✓ in the plan</span> : null}
                    <span className="text-xs tabular-nums">
                      {num(p.impressions)} impressions · position {p.position ?? "–"} · title {p.title_says_topic ? "says" : "does not say"} the topic
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}

      {building ? <p className="mt-3 text-[var(--text-secondary)]">Reading {chosen ? shortPage(chosen) : "the page"}…</p> : null}
      {error ? <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-red-800">{error}</p> : null}

      {bundle && bundle.ok ? (
        <div className="mt-3 border-t border-[var(--border)] pt-3">
          <h5 className="font-semibold">{bundle.draft.title}</h5>
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">Tick what to keep, edit a part's steps if you want it said differently, then confirm. Each thing appears here once.</p>
          <ul className="mt-3 space-y-3">
            {bundle.parts.map((p) => renderPart(p, choices[p.id]?.on ? ++number : null))}
          </ul>
          {bundle.optional.length > 0 ? (
            <>
              <h5 className="mt-4 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Also seen on the page: tick to add</h5>
              <ul className="mt-2 space-y-3">
                {bundle.optional.map((p) => renderPart(p, choices[p.id]?.on ? ++number : null))}
              </ul>
            </>
          ) : null}
          {bundle.left_out.length > 0 ? (
            <p className="mt-3 text-xs text-[var(--text-tertiary)]">Not in this action: {bundle.left_out.map((l) => `${l.id} (${l.reason})`).join(" · ")}</p>
          ) : null}
          <div className="mt-3">
            {inPlan(bundle.page) ? (
              <span className="font-semibold text-green-800">✓ This page is already in the plan.</span>
            ) : (
              <button type="button" onClick={confirm} disabled={pending || kept === 0} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                {pending ? "Adding…" : `Confirm as a growth action (${kept} part${kept === 1 ? "" : "s"})`}
              </button>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
