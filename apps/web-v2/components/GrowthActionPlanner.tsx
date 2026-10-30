"use client";

import { useState, useTransition } from "react";

import { buildGrowthActionAction, confirmTaskAction, topicPagesAction } from "@/app/(app)/[clientSlug]/engine/actions";
import type { EngineTask, GrowthActionBundle, TopicGroup, TopicPages } from "@/lib/engine";

const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString());
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";

/** Plan one page for one topic as a single growth action: the tool picks the page, builds the bundle, a person confirms it. */
export function GrowthActionPlanner({
  clientId,
  month,
  topics,
  tasks,
  focusBucketId,
  onConfirmed,
}: {
  clientId: string;
  month: string;
  topics: TopicGroup[];
  tasks: EngineTask[];
  focusBucketId: string | null;
  onConfirmed: (task: EngineTask) => void;
}) {
  const first = topics.find((g) => g.bucket_id === focusBucketId) ?? topics[0];
  const [keyword, setKeyword] = useState(first?.keywords[0] ?? "");
  const [pages, setPages] = useState<TopicPages | null>(null);
  const [page, setPage] = useState<string | null>(null);
  const [bundle, setBundle] = useState<GrowthActionBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  if (topics.length === 0) return null;
  const inPlan = (url: string) => tasks.find((t) => t.kind === "growth_action" && t.page === url && t.status !== "dropped");

  const choose = (k: string) => {
    setKeyword(k);
    setPages(null);
    setBundle(null);
    setError(null);
  };
  const findPages = () =>
    start(async () => {
      setError(null);
      setBundle(null);
      const r = await topicPagesAction(clientId, keyword);
      if (r.ok) {
        setPages(r.value);
        setPage(r.value.recommended);
      } else setError(r.error);
    });
  const build = () =>
    start(async () => {
      setError(null);
      const r = await buildGrowthActionAction(clientId, keyword, page);
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
        setPages(null);
      } else setError(r.error);
    });

  return (
    <div className="mb-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <h2 className="text-sm font-semibold">Plan a growth action</h2>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        One growth action is one page, worked for one topic: answer the question, use the phrasing people search, add a short FAQ, and whatever else the page needs.
      </p>

      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="font-semibold">Topic</span>
          <select value={keyword} onChange={(e) => choose(e.target.value)} className="ml-2 rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm">
            {topics.map((g) => (
              <optgroup key={g.bucket_id} label={g.bucket}>
                {g.keywords.map((k) => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <button type="button" onClick={findPages} disabled={pending || !keyword} className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm font-semibold disabled:opacity-50">
          {pending && !pages ? "Looking…" : "Find the best page"}
        </button>
      </div>

      {error ? <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}

      {pages ? (
        <div className="mt-4">
          {pages.pages.length === 0 ? (
            <p className="text-sm text-[var(--text-secondary)]">No page shows for “{pages.keyword}” in Search Console over the last three months, so there is no page to work on yet. That is a content job.</p>
          ) : (
            <>
              <p className="text-xs text-[var(--text-tertiary)]">{pages.rule}</p>
              <div className="mt-2 overflow-x-auto">
                <table className="w-full min-w-[34rem] text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                    <tr>
                      <th className="w-6 py-1 pr-2" />
                      <th className="py-1 pr-3 font-medium">Page</th>
                      <th className="px-3 py-1 text-right font-medium">Impressions</th>
                      <th className="px-3 py-1 text-right font-medium">Position</th>
                      <th className="py-1 pl-3 font-medium">Title says the topic</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pages.pages.map((p) => (
                      <tr key={p.url} className="border-t border-[var(--border)] align-top">
                        <td className="py-2 pr-2">
                          <input type="radio" name="topic-page" checked={page === p.url} onChange={() => { setPage(p.url); setBundle(null); }} aria-label={`Work on ${shortPage(p.url)}`} />
                        </td>
                        <td className="py-2 pr-3">
                          <span className="font-medium">{shortPage(p.url)}</span>
                          {p.url === pages.recommended ? <span className="ml-2 rounded bg-green-100 px-1.5 py-0.5 text-xs font-semibold text-green-800">recommended</span> : null}
                          {inPlan(p.url) ? <span className="ml-2 text-xs font-semibold text-green-800">✓ already in the plan</span> : null}
                          <div className="text-xs text-[var(--text-tertiary)]">{p.searches} search{p.searches === 1 ? "" : "es"}, top: “{p.top_search}”</div>
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">{num(p.impressions)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{p.position ?? "–"}</td>
                        <td className="py-2 pl-3 text-xs">{p.title_says_topic ? "yes" : "no"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button type="button" onClick={build} disabled={pending || !page} className="mt-3 rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                {pending && !bundle ? "Reading the page…" : `Build the growth action for ${page ? shortPage(page) : "a page"}`}
              </button>
            </>
          )}
        </div>
      ) : null}

      {bundle && bundle.ok ? (
        <div className="mt-5 border-t border-[var(--border)] pt-4">
          <h3 className="text-sm font-semibold">{bundle.draft.title}</h3>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{bundle.draft.why}</p>
          <ol className="mt-3 space-y-3">
            {bundle.parts.map((p, i) => (
              <li key={p.id} className="rounded-lg bg-[var(--bg)] p-3 text-sm">
                <div className="font-semibold">
                  {i + 1}. {p.name}
                  <span className="ml-2 text-xs font-normal text-[var(--text-tertiary)]">{p.id}{p.core ? "" : " · extra"}{p.confirmed_by_rule ? " · rule" : " · unconfirmed"}</span>
                </div>
                {p.why ? <p className="mt-1 text-[var(--text-secondary)]">{p.why}</p> : null}
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[var(--text-secondary)]">
                  {p.steps.map((s) => <li key={s}>{s}</li>)}
                </ul>
              </li>
            ))}
          </ol>
          {bundle.left_out.length > 0 ? (
            <p className="mt-3 text-xs text-[var(--text-tertiary)]">
              Not in this action: {bundle.left_out.map((l) => `${l.id} (${l.reason})`).join(" · ")}
            </p>
          ) : null}
          {bundle.also_seen.length > 0 ? (
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">Also seen on the page, left out: {bundle.also_seen.map((a) => a.title).join(" · ")}.</p>
          ) : null}
          <div className="mt-3">
            {inPlan(bundle.page) ? (
              <span className="text-sm font-semibold text-green-800">✓ This page is already in the plan.</span>
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
