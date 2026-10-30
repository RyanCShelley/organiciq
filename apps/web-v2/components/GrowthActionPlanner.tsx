"use client";

import { useEffect, useState, useTransition } from "react";

import { buildGrowthActionAction, confirmTaskAction, topicForAction } from "@/app/(app)/[clientSlug]/engine/actions";
import type { CandidateTopic, EngineTask, GrowthActionBundle } from "@/lib/engine";

const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString());
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";

/**
 * Plan a growth action from a diagnosed candidate. The candidate's topic is worked out, the best page for
 * it is shown beside the candidate's own, and a person chooses which page to work, one growth action at a time.
 */
export function GrowthActionPlanner({
  clientId,
  month,
  search,
  page,
  tasks,
  onConfirmed,
}: {
  clientId: string;
  month: string;
  search: string;
  page: string;
  tasks: EngineTask[];
  onConfirmed: (task: EngineTask) => void;
}) {
  const [topic, setTopic] = useState<CandidateTopic | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [bundle, setBundle] = useState<GrowthActionBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  const inPlan = (url: string) => tasks.find((t) => t.kind === "growth_action" && t.page === url && t.status !== "dropped");
  const pages = topic?.pages;

  const build = () =>
    start(async () => {
      if (!topic?.keyword) return;
      setError(null);
      const r = await buildGrowthActionAction(clientId, topic.keyword, chosen);
      setBundle(r);
      if (!r.ok) setError(r.error);
    });
  const confirm = () =>
    start(async () => {
      if (!bundle || !bundle.ok) return;
      const r = await confirmTaskAction(clientId, month, bundle.draft);
      if (r.ok) {
        onConfirmed(r.value);
        setBundle(null);
      } else setError(r.error);
    });

  return (
    <div className="mt-4 rounded-lg border border-[var(--brand-teal)] p-4 text-sm">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--brand-teal)]">Plan a growth action</h4>
      {!topic && !error ? <p className="mt-2 text-[var(--text-secondary)]">Finding the best page for this topic…</p> : null}
      {topic && !topic.keyword ? <p className="mt-2 text-[var(--text-secondary)]">{topic.source}, so there is no topic to plan around.</p> : null}

      {topic?.keyword && pages ? (
        <>
          <p className="mt-2 text-[var(--text-secondary)]">
            Topic: <strong>{topic.keyword}</strong> <span className="text-xs text-[var(--text-tertiary)]">({topic.source})</span>.{" "}
            {pages.recommended === page
              ? "This page is the best one for the topic."
              : pages.recommended
                ? `The best page for it is ${shortPage(pages.recommended)}, not this one.`
                : "No page shows for it."}
          </p>
          {pages.pages.length > 0 ? (
            <>
              <p className="mt-1 text-xs text-[var(--text-tertiary)]">{pages.rule}</p>
              <ul className="mt-2 divide-y divide-[var(--border)]">
                {pages.pages.slice(0, 5).map((p) => (
                  <li key={p.url} className="flex flex-wrap items-center gap-3 py-1.5">
                    <input
                      type="radio"
                      name={`pick-${search}-${page}`}
                      checked={chosen === p.url}
                      onChange={() => {
                        setChosen(p.url);
                        setBundle(null);
                      }}
                      aria-label={`Work on ${shortPage(p.url)}`}
                    />
                    <span className="min-w-0 flex-1 break-all font-medium">{shortPage(p.url)}</span>
                    {p.url === pages.recommended ? <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs font-semibold text-green-800">best page</span> : null}
                    {p.url === page ? <span className="rounded bg-[var(--bg)] px-1.5 py-0.5 text-xs font-semibold">this candidate</span> : null}
                    {inPlan(p.url) ? <span className="text-xs font-semibold text-green-800">✓ in the plan</span> : null}
                    <span className="text-xs tabular-nums text-[var(--text-secondary)]">
                      {num(p.impressions)} impressions · position {p.position ?? "–"} · title {p.title_says_topic ? "says" : "does not say"} the topic
                    </span>
                  </li>
                ))}
              </ul>
              <button type="button" onClick={build} disabled={pending || !chosen} className="mt-3 rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                {pending && !bundle ? "Reading the page…" : `Build the growth action for ${chosen ? shortPage(chosen) : "a page"}`}
              </button>
            </>
          ) : null}
        </>
      ) : null}

      {error ? <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-red-800">{error}</p> : null}

      {bundle && bundle.ok ? (
        <div className="mt-4 border-t border-[var(--border)] pt-3">
          <h5 className="font-semibold">{bundle.draft.title}</h5>
          <p className="mt-1 text-[var(--text-secondary)]">{bundle.draft.why}</p>
          <ol className="mt-3 space-y-3">
            {bundle.parts.map((p, i) => (
              <li key={p.id} className="rounded-lg bg-[var(--bg)] p-3">
                <div className="font-semibold">
                  {i + 1}. {p.name}
                  <span className="ml-2 text-xs font-normal text-[var(--text-tertiary)]">
                    {p.id}
                    {p.core ? "" : " · extra"}
                    {p.confirmed_by_rule ? " · rule" : " · unconfirmed"}
                  </span>
                </div>
                {p.why ? <p className="mt-1 text-[var(--text-secondary)]">{p.why}</p> : null}
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[var(--text-secondary)]">
                  {p.steps.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
          {bundle.left_out.length > 0 ? (
            <p className="mt-3 text-xs text-[var(--text-tertiary)]">Not in this action: {bundle.left_out.map((l) => `${l.id} (${l.reason})`).join(" · ")}</p>
          ) : null}
          {bundle.also_seen.length > 0 ? (
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">Also seen on the page, left out: {bundle.also_seen.map((a) => a.title).join(" · ")}.</p>
          ) : null}
          <div className="mt-3">
            {inPlan(bundle.page) ? (
              <span className="font-semibold text-green-800">✓ This page is already in the plan.</span>
            ) : (
              <button type="button" onClick={confirm} disabled={pending} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                {pending ? "Adding…" : "Confirm as a growth action"}
              </button>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
