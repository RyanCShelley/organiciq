"use client";

import { useEffect, useMemo, useState, useTransition } from "react";

import { buildGrowthActionAction, confirmTaskAction, topicForAction } from "@/app/(app)/[clientSlug]/engine/actions";
import type { ActionContext, CandidateTopic, Winners, EngineTask, GrowthActionBundle, GrowthPart, TaskDraft } from "@/lib/engine";
import { Spinner } from "@/components/ui/Spinner";

const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString());
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";

type Choice = { on: boolean; editing: boolean; text: string };

/** The task as the person left it: only the ticked parts, with their steps as edited. */
export function assemble(bundle: Extract<GrowthActionBundle, { ok: true }>, parts: GrowthPart[], choices: Record<string, Choice>): TaskDraft {
  const chosen = parts.filter((p) => choices[p.id]?.on);
  const steps: string[] = [];
  chosen.forEach((p, i) => {
    steps.push(`# ${i + 1}. ${p.name}`);
    steps.push(...choices[p.id].text.split("\n").map((l) => l.trim()).filter(Boolean));
  });
  // The draft's own lines about a part that was unticked are dropped; the lines about the search, the page and the read are kept.
  const dropped = parts.filter((p) => !choices[p.id]?.on).map((p) => `${p.name}: `);
  const added = chosen.filter((p) => !bundle.parts.some((b) => b.id === p.id)).flatMap((p) => p.evidence.map((e) => `${p.name}: ${e}`));
  const draft = bundle.draft!; // Only called to confirm, and there is nothing to confirm without a draft.
  const evidence = [...draft.evidence.filter((e) => !dropped.some((d) => e.startsWith(d))), ...added].filter(Boolean);
  // An investigation says why in its own words, which the usual sentence would contradict.
  const special = bundle.parts.some((p) => p.id === "TI-1");
  return {
    ...draft,
    why: special
      ? draft.why
      : `This page gets the most impressions for “${bundle.keyword}” (${bundle.chosen.impressions.toLocaleString()} over three months). The work is ${chosen.length} part${chosen.length === 1 ? "" : "s"}, done together on this one page: ${chosen.map((p) => p.name.toLowerCase()).join(", ")}.`,
    steps,
    evidence,
    parts: chosen.map((p) => ({ id: p.id, name: p.name })),
  };
}

const FIT_WORDS: Record<string, string> = { high: "suits the search", medium: "partly suits the search", low: "does not suit the search", unverified: "fit not judged" };
const STATE_MARK: Record<string, string> = { pass: "✓", unverified: "?", fail: "✕" };

const host = (url: string) => url.replace(/^https?:\/\/(www\.)?/, "").split("/")[0];

/** Who is winning for the term, in search and in the AI platforms, and whether this is the page to win it with. */
function WinnersView({ winners }: { winners: Winners }) {
  const { search, llm, comparison } = winners;
  const unread = [...search.pages, ...llm.pages].filter((p) => !p.read);
  return (
    <details className="mt-2">
      <summary className="cursor-pointer font-semibold">
        Who is winning
        {comparison.best_page ? ` · this page is ${comparison.best_page.verdict === "yes" ? "the right one" : comparison.best_page.verdict === "partly" ? "partly right" : "not the right one"}` : ""}
      </summary>
      <div className="mt-2 space-y-2 text-[var(--text-secondary)]">
        {comparison.best_page ? <p><strong>Is this the best page?</strong> {comparison.best_page.why}</p> : null}
        {!comparison.ok ? <p>{comparison.reason}</p> : null}
        {search.ranked.length > 0 ? (
          <div>
            <strong>In search.</strong>
            {search.client_ranks.length > 0 ? ` This site ranks at ${search.client_ranks.map((r) => `#${r.rank}`).join(", ")}.` : " This site is not in the top results."}
            <ol className="mt-1 space-y-0.5">
              {search.ranked.map((r) => (
                <li key={r.url}>
                  {r.rank}. <span className="font-medium">{r.domain}</span> · {[r.content_type, r.content_style].filter(Boolean).join(", ") || "type not read"} · <span className="text-[var(--text-tertiary)]">{r.title}</span>
                </li>
              ))}
            </ol>
          </div>
        ) : null}
        {llm.ok && llm.platforms ? (
          <div>
            <strong>In the AI platforms</strong> (prompt “{llm.prompt}”, run of {llm.run_date}).
            <ul className="mt-1 space-y-0.5">
              {llm.platforms.map((p) => (
                <li key={p.platform}>
                  <span className="font-medium">{p.platform}</span>: {p.client_cited ? "cites this site" : "does not cite this site"}, {p.brand_mentioned ? `names the brand${p.brand_rank ? ` (${p.brand_rank} of ${p.total_brands})` : ""}` : "does not name the brand"}
                  {p.brands.length > 0 ? ` · brands named: ${p.brands.join(", ")}` : ""}
                </li>
              ))}
            </ul>
            {llm.cited_pages && llm.cited_pages.length > 0 ? <p className="mt-1">Pages cited: {llm.cited_pages.slice(0, 6).map((c) => `${c.domain}${c.own ? " (this site)" : ""}`).join(", ")}.</p> : null}
          </div>
        ) : (
          <p><strong>In the AI platforms.</strong> {llm.reason ?? "No data."}</p>
        )}
        <p>
          <strong>Winning pages read:</strong> {[...search.pages, ...llm.pages].filter((p) => p.read).map((p) => host(p.url)).join(", ") || "none"}.
          {unread.length > 0 ? ` Not read: ${unread.map((p) => `${host(p.url)} (${p.reason})`).join(" ")}` : ""}
        </p>
      </div>
    </details>
  );
}

/** What the action was judged on: one line always, the detail on request. */
function ContextSummary({ context }: { context: ActionContext }) {
  const { intent, page_type, fit, evidence, validation, template, winners } = context;
  const tone = validation.verdict === "publish" ? "bg-green-50 text-green-900" : validation.verdict === "reject" ? "bg-red-50 text-red-800" : "bg-amber-50 text-amber-900";
  return (
    <div className="mt-3 rounded-lg bg-[var(--bg)] p-3 text-xs">
      <p className="text-[var(--text-secondary)]">
        Search intent: <strong>{intent.name}</strong>
        {intent.read ? ` (${intent.secondary ? `secondary ${intent.secondary}, ` : ""}${intent.confidence} confidence)` : ""} · Page type: <strong>{page_type.name}</strong> ·{" "}
        <strong>{FIT_WORDS[fit.level]}</strong> · Crawl status: <strong>{evidence.crawl_status_name}</strong> · Evidence confidence: <strong>{evidence.confidence}</strong>
      </p>
      <p className={`mt-2 rounded px-2 py-1 ${tone}`}>{validation.summary}</p>
      {winners ? <WinnersView winners={winners} /> : null}
      {evidence.unverified.length > 0 ? (
        <ul className="mt-2 list-disc pl-5 text-[var(--text-secondary)]">
          {evidence.unverified.map((u) => (
            <li key={u}>Unverified: {u}</li>
          ))}
        </ul>
      ) : null}
      <details className="mt-2">
        <summary className="cursor-pointer font-semibold">How this was judged</summary>
        <div className="mt-2 space-y-2 text-[var(--text-secondary)]">
          <p>
            <strong>What the searcher wants.</strong> {intent.searcher_goal ?? "Not read."}
          </p>
          <p>
            <strong>What the results page shows{intent.serp_date ? ` (${intent.serp_date})` : ""}.</strong>{" "}
            {intent.evidence.length > 0 ? intent.evidence.join(". ") + "." : intent.uncertainty ?? "Nothing was read."}
            {Object.keys(intent.content_types).length > 0 ? ` Ranking types: ${Object.entries(intent.content_types).map(([t, n]) => `${n} ${t}`).join(", ")}.` : ""}
            {Object.keys(intent.content_styles).length > 0 ? ` Styles: ${Object.entries(intent.content_styles).map(([t, n]) => `${n} ${t}`).join(", ")}.` : ""}
            {intent.features.length > 0 ? ` Features: ${intent.features.map((f) => f.replaceAll("_", " ")).join(", ")}.` : ""}
            {intent.read && intent.uncertainty ? ` Unclear: ${intent.uncertainty}` : ""}
          </p>
          {intent.labels.length > 0 ? (
            <p>
              <strong>Keyword-tool labels (reference only).</strong> {intent.labels.join(", ")}. {intent.label_disagreement ?? ""}
            </p>
          ) : null}
          {intent.consumer_need ? (
            <p>
              <strong>Consumer need ({intent.consumer_need.basis}).</strong> {intent.consumer_need.name}. {intent.consumer_need.evidence}
            </p>
          ) : null}
          <p>
            <strong>Page type.</strong> {page_type.name}
            {page_type.basis.length > 0 ? `, from ${page_type.basis.join(" and ")}` : ""}. {page_type.note ?? `It is there to ${page_type.purpose}.`}
          </p>
          <p>
            <strong>Fit.</strong> {fit.why}
          </p>
          <p>
            <strong>Template.</strong> {template.note}
          </p>
          <p>
            <strong>Evidence.</strong> {evidence.summary}
          </p>
          <ul className="space-y-0.5">
            {validation.checks.map((c) => (
              <li key={c.key}>
                {STATE_MARK[c.state]} {c.question} <span className="text-[var(--text-tertiary)]">{c.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      </details>
    </div>
  );
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
  const [showAll, setShowAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [pending, start] = useTransition();

  useEffect(() => {
    let live = true;
    topicForAction(clientId, search, page).then((r) => {
      if (!live) return;
      if (r.ok) {
        setTopic(r.value);
        // The page the person selected is the page worked on. A better one is offered, never switched to.
        setChosen(page);
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
    buildGrowthActionAction(clientId, topic.keyword, chosen, focus, page, topic.search ?? null).then((r) => {
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
  // Once the action is built its page list carries the fit read from the term's own results page.
  const pages = (bundle && bundle.ok && bundle.topic) || topic?.pages;
  const better = bundle && bundle.ok ? bundle.better_page : null;
  const suggested = bundle && bundle.ok ? bundle.suggested_page : null;
  const nothing = bundle && bundle.ok ? bundle.nothing_recommended : null;
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
            </span>
          </label>
          {c.on ? (
            <button type="button" onClick={() => set(p.id, { editing: !c.editing })} className="text-xs font-semibold underline">
              {c.editing ? "Done editing" : "Edit steps"}
            </button>
          ) : null}
        </div>
        {p.action_type || p.scope ? (
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
            {[p.action_type, p.scope, p.benefit ? `for ${p.benefit}` : null].filter(Boolean).join(" · ")}
          </p>
        ) : null}
        {p.why ? <p className="mt-1 text-[var(--text-secondary)]">{p.why}</p> : null}
        {p.note && (p.scope !== "page-specific" || /template/i.test(p.note)) ? <p className="mt-1 text-xs text-[var(--text-secondary)]">Where: {p.note}</p> : null}
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
      {!topic && !error ? <p className="mt-2 text-[var(--text-secondary)]">Loading the search and the page…</p> : null}
      {topic && !topic.keyword ? <p className="mt-2 text-[var(--text-secondary)]">{topic.source}, so there is no topic to plan around.</p> : null}

      {topic?.keyword && pages ? (
        <div className="mt-2 text-[var(--text-secondary)]">
          {topic.search ? (
            <>
              Search: <strong>{topic.search}</strong> <span className="text-xs text-[var(--text-tertiary)]">(the search you selected, under the watchlist keyword “{topic.keyword}”)</span>.
            </>
          ) : (
            <>
              Watchlist keyword: <strong>{topic.keyword}</strong> <span className="text-xs text-[var(--text-tertiary)]">({topic.source})</span>.
              {bundle && bundle.ok ? <> Search used: <strong>{bundle.search}</strong> <span className="text-xs text-[var(--text-tertiary)]">({bundle.search_source})</span>.</> : null}
            </>
          )}{" "}
          Page: <strong>{shortPage(chosen ?? page)}</strong>
          {chosen && chosen !== page ? <span className="text-xs text-[var(--text-tertiary)]"> (you switched from {shortPage(page)})</span> : null}.{" "}
          {better ? (
            <span className="mt-1 block rounded bg-amber-50 px-2 py-1 text-amber-900">
              Another page may serve this search better: <strong>{shortPage(better.url)}</strong>. {better.why}{" "}
              <button type="button" onClick={() => setChosen(better.url)} className="font-semibold underline">
                Work on that page instead
              </button>
            </span>
          ) : null}
          {suggested ? (
            <span className="mt-1 block rounded bg-amber-50 px-2 py-1 text-amber-900">
              {suggested.url ? <><strong>{shortPage(suggested.url)}</strong>: </> : null}{suggested.why} {suggested.next}{" "}
              {suggested.url && pages.pages.some((p) => p.url === suggested.url) ? (
                <button type="button" onClick={() => setChosen(suggested.url!)} className="font-semibold underline">
                  Review that page
                </button>
              ) : null}
            </span>
          ) : null}
          {pages.pages.length > 1 ? (
            <button type="button" onClick={() => setShowPages((v) => !v)} className="text-xs font-semibold underline">
              {showPages ? "Hide the pages" : `Choose a different page (${pages.pages.length})`}
            </button>
          ) : null}
          {showPages ? (
            <>
              <p className="mt-1 text-xs text-[var(--text-tertiary)]">{pages.rule}</p>
              <ul className="mt-2 divide-y divide-[var(--border)]">
                {(showAll ? pages.pages : [...pages.pages.slice(0, 6), ...pages.pages.slice(6).filter((p) => p.url === page)]).map((p) => (
                  <li key={p.url} className="flex flex-wrap items-center gap-3 py-1.5">
                    <input type="radio" name={`pick-${search}-${page}`} checked={chosen === p.url} onChange={() => setChosen(p.url)} aria-label={`Work on ${shortPage(p.url)}`} />
                    <span className="min-w-0 flex-1 break-all font-medium">{shortPage(p.url)}</span>
                    {p.fit === "high" ? <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs font-semibold text-green-800" title={p.fit_why}>suits the search</span> : null}
                    {p.url === page ? <span className="rounded bg-[var(--bg)] px-1.5 py-0.5 text-xs font-semibold">the page you selected</span> : null}
                    {inPlan(p.url) ? <span className="text-xs font-semibold text-green-800">✓ in the plan</span> : null}
                    <span className="text-xs tabular-nums">
                      {num(p.impressions)} impressions · position {p.position ?? "–"} · {p.title_read === false ? "title not read (the site turned our crawler away)" : `title ${p.title_says_topic ? "says" : "does not say"} the topic`}
                      {p.page_type_name && p.page_type !== "unknown" ? ` · ${p.page_type_name.toLowerCase()}` : ""}
                    </span>
                    {p.fit === "low" ? <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-semibold text-amber-900" title={p.fit_why}>does not suit the search</span> : null}
                  </li>
                ))}
              </ul>
              {pages.pages.length > 6 ? (
                <button type="button" onClick={() => setShowAll((v) => !v)} className="mt-2 text-xs font-semibold underline">
                  {showAll ? "Show fewer pages" : `Show all ${pages.pages.length} pages`}
                </button>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}

      {building ? <p className="mt-3 text-[var(--text-secondary)]">Reading {chosen ? shortPage(chosen) : "the page"}…</p> : null}
      {error ? <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-red-800">{error}</p> : null}
      {bundle && !bundle.ok && bundle.context ? <ContextSummary context={bundle.context} /> : null}

      {bundle && bundle.ok ? (
        <div className="mt-3 border-t border-[var(--border)] pt-3">
          <h5 className="font-semibold">{nothing ? "Nothing recommended for this page and search" : bundle.draft?.title}</h5>
          {nothing ? <p className="mt-1">{nothing.reason}</p> : null}
          {bundle.context ? <ContextSummary context={bundle.context} /> : null}
          {nothing ? null : <p className="mt-1 text-xs text-[var(--text-tertiary)]">Check what to keep, edit a part's steps if you want it said differently, then confirm. Each thing appears here once.</p>}
          <ul className="mt-3 space-y-3">
            {bundle.parts.map((p) => renderPart(p, choices[p.id]?.on ? ++number : null))}
          </ul>
          {bundle.optional.length > 0 ? (
            <>
              <h5 className="mt-4 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Optional: tick to add</h5>
              <ul className="mt-2 space-y-3">
                {bundle.optional.map((p) => renderPart(p, choices[p.id]?.on ? ++number : null))}
              </ul>
            </>
          ) : null}
          {bundle.left_out.length > 0 ? (
            <p className="mt-3 text-xs text-[var(--text-tertiary)]">Not in this action: {bundle.left_out.map((l) => `${l.name} (${l.reason})`).join(" · ")}</p>
          ) : null}
          <div className="mt-3">
            {inPlan(bundle.page) ? (
              <span className="font-semibold text-green-800">✓ This page is already in the plan.</span>
            ) : nothing ? null : (
              <button type="button" onClick={confirm} disabled={pending || kept === 0} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                {pending ? <><Spinner />Adding…</> : `Confirm as a growth action (${kept} part${kept === 1 ? "" : "s"})`}
              </button>
            )}
            {!inPlan(bundle.page) && kept === 0 && !nothing ? <p className="mt-2 text-xs text-[var(--text-secondary)]">Nothing here to confirm: no part applies to this page. Choose a different page, or see why each part was left out above.</p> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
