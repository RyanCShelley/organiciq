"use client";

import { useEffect, useMemo, useState, useTransition } from "react";

import {
  buildGrowthActionAction,
  confirmTaskAction,
  rejectTaskAction,
  topicForAction,
} from "@/app/(app)/[clientSlug]/engine/actions";
import { ChecklistPanel } from "@/components/diagnose/ChecklistPanel";
import { ContextHeader } from "@/components/diagnose/ContextHeader";
import { PageHistoryPanel } from "@/components/diagnose/PageHistoryPanel";
import { StyleNotesBanner } from "@/components/diagnose/StyleNotesBanner";
import { Spinner } from "@/components/ui/Spinner";
import {
  REJECTION_REASONS,
  type ActionContext,
  type CandidateTopic,
  type EngineTask,
  type GrowthActionBundle,
  type GrowthPart,
  type PriorRejection,
  type RejectionReason,
  type TaskDraft,
  type Winners,
} from "@/lib/engine";

const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString());
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";

type Choice = { on: boolean; editing: boolean; text: string };

/** The task as the person left it: only the ticked parts, with their steps as edited. */
export function assemble(
  bundle: Extract<GrowthActionBundle, { ok: true }>,
  parts: GrowthPart[],
  choices: Record<string, Choice>,
): TaskDraft {
  const chosen = parts.filter((p) => choices[p.id]?.on);
  const steps: string[] = [];
  chosen.forEach((p, i) => {
    steps.push(`# ${i + 1}. ${p.name}`);
    steps.push(...(choices[p.id]?.text ?? p.steps.join("\n")).split("\n").map((l) => l.trim()).filter(Boolean));
  });
  // The draft's own lines about a part that was unticked are dropped; the lines about the search, the page and the read are kept.
  const dropped = parts.filter((p) => !choices[p.id]?.on).map((p) => `${p.name}: `);
  const added = chosen
    .filter((p) => !bundle.parts.some((b) => b.id === p.id))
    .flatMap((p) => (p.evidence ?? []).map((e) => `${p.name}: ${e}`));
  const draft: TaskDraft = bundle.draft ?? {
    kind: "growth_action",
    rule_id: "GA",
    search: bundle.keyword,
    page: bundle.page,
    title: `Growth action: ${shortPage(bundle.page)} for “${bundle.keyword}”`,
    why: null,
    steps: [],
    done_when: "Every part above is live on the page.",
    metric: null,
    effort_min: null,
    evidence: [],
  };
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
    parts: chosen.map((p) => ({
      id: p.custom ? "CUSTOM" : p.id,
      name: p.name,
      ...(p.custom ? { custom: true } : {}),
    })),
  };
}

const FIT_WORDS: Record<string, string> = {
  high: "suits the search",
  medium: "partly suits the search",
  low: "does not suit the search",
  unverified: "fit not judged",
};
const STATE_MARK: Record<string, string> = { pass: "✓", unverified: "?", fail: "✕" };

const host = (url: string) => url.replace(/^https?:\/\/(www\.)?/, "").split("/")[0];

/** Who is winning for the term, in search and in the AI platforms, and whether this is the page to win it with. */
function WinnersView({ winners, hideQuestions = false }: { winners: Winners; hideQuestions?: boolean }) {
  const { search, llm, comparison } = winners;
  const unread = [...search.pages, ...llm.pages].filter((p) => !p.read);
  const questions = comparison.questions;

  return (
    <details className="mt-2 rounded-[10px] border border-[#ececec] bg-white px-3 py-2">
      <summary className="cursor-pointer font-semibold text-[#0a0c0f]">
        Who is winning
        {comparison.best_page
          ? ` · this page is ${comparison.best_page.verdict === "yes" ? "the right one" : comparison.best_page.verdict === "partly" ? "partly right" : "not the right one"}`
          : ""}
        {questions && questions.missing.length > 0 ? ` · ${questions.missing.length} unanswered PAA/questions` : ""}
      </summary>
      <div className="mt-2.5 space-y-2.5 text-xs text-[#4a5560]">
        {comparison.best_page ? (
          <p>
            <strong className="text-[#0a0c0f]">Is this the best page?</strong> {comparison.best_page.why}
          </p>
        ) : null}
        {!comparison.ok ? <p>{comparison.reason}</p> : null}

        {!hideQuestions && questions ? (
          <div className="rounded-[10px] border border-[#ececec] bg-[#f8f8f8] p-2.5">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
              People Also Ask &amp; searcher questions ({questions.checked} checked)
            </div>
            {questions.missing.length > 0 ? (
              <ul className="mt-1.5 space-y-1.5">
                {questions.missing.map((q) => (
                  <li key={q.question} className="rounded-lg border border-[#ececec] bg-white px-2.5 py-1.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="rounded-full bg-[#e6f7f5] px-2 py-0 text-[10px] font-semibold text-[#00665f]">
                        {q.source_name}
                      </span>
                      {q.detail ? <span className="text-[11px] text-[#7a838c]">{q.detail}</span> : null}
                    </div>
                    <div className="mt-1 font-semibold text-[#0a0c0f]">“{q.question}”</div>
                    {q.why ? <p className="mt-0.5 text-[#4a5560]">{q.why}</p> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-[#00665f]">All {questions.checked} checked questions are already answered on this page.</p>
            )}
          </div>
        ) : null}

        {search.ranked.length > 0 ? (
          <div>
            <strong className="text-[#0a0c0f]">In search.</strong>
            {search.client_ranks.length > 0
              ? ` This site ranks at ${search.client_ranks.map((r) => `#${r.rank}`).join(", ")}.`
              : " This site is not in the top results."}
            <ol className="mt-1 space-y-0.5">
              {search.ranked.map((r) => (
                <li key={r.url}>
                  {r.rank}. <span className="font-medium text-[#171a22]">{r.domain}</span> ·{" "}
                  {[r.content_type, r.content_style].filter(Boolean).join(", ") || "type not read"} ·{" "}
                  <span className="text-[#7a838c]">{r.title}</span>
                </li>
              ))}
            </ol>
          </div>
        ) : null}
        {llm.ok && llm.platforms ? (
          <div>
            <strong className="text-[#0a0c0f]">In the AI platforms</strong> (prompt “{llm.prompt}”, run of {llm.run_date}).
            <ul className="mt-1 space-y-0.5">
              {llm.platforms.map((p) => (
                <li key={p.platform}>
                  <span className="font-medium text-[#171a22]">{p.platform}</span>:{" "}
                  {p.client_cited ? "cites this site" : "does not cite this site"},{" "}
                  {p.brand_mentioned
                    ? `names the brand${p.brand_rank ? ` (${p.brand_rank} of ${p.total_brands})` : ""}`
                    : "does not name the brand"}
                  {p.brands.length > 0 ? ` · brands named: ${p.brands.join(", ")}` : ""}
                </li>
              ))}
            </ul>
            {llm.cited_pages && llm.cited_pages.length > 0 ? (
              <p className="mt-1">
                Pages cited: {llm.cited_pages.slice(0, 6).map((c) => `${c.domain}${c.own ? " (this site)" : ""}`).join(", ")}.
              </p>
            ) : null}
          </div>
        ) : (
          <p>
            <strong className="text-[#0a0c0f]">In the AI platforms.</strong> {llm.reason ?? "No data."}
          </p>
        )}
        <p>
          <strong className="text-[#0a0c0f]">Winning pages read:</strong>{" "}
          {[...search.pages, ...llm.pages].filter((p) => p.read).map((p) => host(p.url)).join(", ") || "none"}.
          {unread.length > 0 ? ` Not read: ${unread.map((p) => `${host(p.url)} (${p.reason})`).join(" ")}` : ""}
        </p>
      </div>
    </details>
  );
}

/** What the action was judged on: one line always, the detail on request. */
function ContextSummary({
  context,
  focusOrderReason,
  hideQuestions = false,
}: {
  context: ActionContext;
  focusOrderReason?: string | null;
  hideQuestions?: boolean;
}) {
  const { intent, page_type, fit, evidence, validation, template, winners } = context;
  const tone =
    validation.verdict === "publish"
      ? "border-[#bfe9e4] bg-[#e6f7f5] text-[#00665f]"
      : validation.verdict === "reject"
        ? "border-[oklch(0.88_0.06_25)] bg-[oklch(0.965_0.025_25)] text-[oklch(0.48_0.17_25)]"
        : "border-[oklch(0.88_0.08_85)] bg-[oklch(0.97_0.045_85)] text-[oklch(0.42_0.1_65)]";
  return (
    <div className="mt-3 space-y-2.5 text-xs">
      <ContextHeader
        intent={intent}
        pageType={page_type}
        fit={fit}
        template={template}
        focus={context.focus}
        focusOrderReason={focusOrderReason}
      />

      <p className={`rounded-[10px] border px-3 py-2 text-xs font-medium ${tone}`}>{validation.summary}</p>
      <p className="text-[11px] text-[#7a838c]">
        Search intent: <strong>{intent.name}</strong> · Page type: <strong>{page_type.name}</strong> ·{" "}
        <strong>{FIT_WORDS[fit.level]}</strong> · Crawl status: <strong>{evidence.crawl_status_name}</strong> · Evidence confidence:{" "}
        <strong>{evidence.confidence}</strong>
      </p>

      {winners ? <WinnersView winners={winners} hideQuestions={hideQuestions} /> : null}

      {evidence.unverified.length > 0 ? (
        <ul className="list-disc space-y-0.5 pl-5 text-[#4a5560]">
          {evidence.unverified.map((u) => (
            <li key={u}>Unverified: {u}</li>
          ))}
        </ul>
      ) : null}

      <details className="rounded-[10px] border border-[#ececec] bg-white px-3 py-2">
        <summary className="cursor-pointer font-semibold text-[#0a0c0f]">How this was judged</summary>
        <div className="mt-2 space-y-2 text-[#4a5560]">
          <p>
            <strong className="text-[#171a22]">What the searcher wants.</strong> {intent.searcher_goal ?? "Not read."}
          </p>
          <p>
            <strong className="text-[#171a22]">What the results page shows{intent.serp_date ? ` (${intent.serp_date})` : ""}.</strong>{" "}
            {intent.evidence.length > 0 ? intent.evidence.join(". ") + "." : intent.uncertainty ?? "Nothing was read."}
            {Object.keys(intent.content_types).length > 0
              ? ` Ranking types: ${Object.entries(intent.content_types).map(([t, n]) => `${n} ${t}`).join(", ")}.`
              : ""}
            {Object.keys(intent.content_styles).length > 0
              ? ` Styles: ${Object.entries(intent.content_styles).map(([t, n]) => `${n} ${t}`).join(", ")}.`
              : ""}
            {intent.features.length > 0 ? ` Features: ${intent.features.map((f) => f.replaceAll("_", " ")).join(", ")}.` : ""}
            {intent.read && intent.uncertainty ? ` Unclear: ${intent.uncertainty}` : ""}
          </p>
          {intent.labels.length > 0 ? (
            <p>
              <strong className="text-[#171a22]">Keyword-tool labels (reference only).</strong> {intent.labels.join(", ")}.{" "}
              {intent.label_disagreement ?? ""}
            </p>
          ) : null}
          {intent.consumer_need ? (
            <p>
              <strong className="text-[#171a22]">Consumer need ({intent.consumer_need.basis}).</strong> {intent.consumer_need.name}.{" "}
              {intent.consumer_need.evidence}
            </p>
          ) : null}
          <p>
            <strong className="text-[#171a22]">Page type.</strong> {page_type.name}
            {page_type.basis.length > 0 ? `, from ${page_type.basis.join(" and ")}` : ""}.{" "}
            {page_type.note ?? `It is there to ${page_type.purpose}.`}
          </p>
          <p>
            <strong className="text-[#171a22]">Fit.</strong> {fit.why}
          </p>
          <p>
            <strong className="text-[#171a22]">Template.</strong> {template.note}
          </p>
          <p>
            <strong className="text-[#171a22]">Evidence.</strong> {evidence.summary}
          </p>
          <ul className="space-y-0.5">
            {validation.checks.map((c) => (
              <li key={c.key}>
                {STATE_MARK[c.state]} {c.question} <span className="text-[#7a838c]">{c.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      </details>
    </div>
  );
}

function PriorRejectionsBanner({ rejections }: { rejections: PriorRejection[] | undefined }) {
  if (!rejections || rejections.length === 0) return null;
  return (
    <div className="rounded-xl border border-[oklch(0.88_0.06_25)] bg-[oklch(0.965_0.025_25)] p-3.5 text-xs">
      <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[oklch(0.48_0.17_25)]">
        Prior rejections on this page ({rejections.length})
      </div>
      <ul className="mt-2 space-y-1.5">
        {rejections.map((r) => (
          <li key={r.id} className="rounded-lg border border-[oklch(0.88_0.06_25)] bg-white px-3 py-2 text-[#171a22]">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold">{r.title}</span>
              <span className="rounded-full bg-[oklch(0.965_0.025_25)] px-2 py-0.5 text-[10px] font-semibold text-[oklch(0.48_0.17_25)]">
                {r.rejection_reason_label ?? r.rejection_reason ?? "Rejected"}
              </span>
            </div>
            {r.rejection_note ? <p className="mt-1 text-[#4a5560]">{r.rejection_note}</p> : null}
            <div className="mt-0.5 text-[11px] text-[#7a838c]">
              {r.month} · “{r.search}”{r.rejected_by ? ` · by ${r.rejected_by}` : ""}
              {r.rejected_at ? ` · ${r.rejected_at.slice(0, 10)}` : ""}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function partBadge(p: GrowthPart): { label: string; cls: string } | null {
  if (p.custom) return { label: "Custom step", cls: "bg-[#223540] text-white" };
  if (p.id === "MC-1") return { label: "Meta & CTR", cls: "bg-[#e6f7f5] text-[#00665f]" };
  if (p.id === "FQ-1") return { label: "FAQ page link", cls: "bg-[#e6f7f5] text-[#00665f]" };
  if (p.id === "S-2") return { label: "FAQ & PAA", cls: "bg-[#e9fedc] text-[#2f5a00]" };
  if (p.role === "primary") return { label: "Primary", cls: "bg-[#e6f7f5] text-[#00665f]" };
  return null;
}

/**
 * Plan a growth action from a diagnosed candidate. The candidate's topic is worked out, the best page for it is
 * shown beside the candidate's own, and everything worth doing to the chosen page appears once, here: tick what
 * to keep, edit the steps, add custom steps, reject with a reason, or confirm.
 */
export function GrowthActionPlanner({
  clientId,
  month,
  search,
  page,
  focus,
  tasks,
  rejectionReasons,
  onConfirmed,
}: {
  clientId: string;
  month: string;
  search: string;
  page: string;
  focus: "visibility" | "traffic" | "leads";
  tasks: EngineTask[];
  rejectionReasons?: RejectionReason[];
  onConfirmed: (task: EngineTask) => void;
}) {
  const reasons = rejectionReasons && rejectionReasons.length > 0 ? rejectionReasons : REJECTION_REASONS;
  const [topic, setTopic] = useState<CandidateTopic | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [bundle, setBundle] = useState<GrowthActionBundle | null>(null);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [customParts, setCustomParts] = useState<GrowthPart[]>([]);
  const [customTitle, setCustomTitle] = useState("");
  const [customStepsText, setCustomStepsText] = useState("");
  const [showCustomForm, setShowCustomForm] = useState(false);

  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectReason, setRejectReason] = useState<string>(reasons[0]?.key ?? "wrong_intent");
  const [rejectNote, setRejectNote] = useState("");
  const [rejectedMessage, setRejectedMessage] = useState<string | null>(null);

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
    setRejectedMessage(null);
    setCustomParts([]);
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

  const inPlan = (url: string) =>
    tasks.find((t) => t.kind === "growth_action" && t.page === url && t.status !== "dropped" && t.status !== "rejected");
  const pages = (bundle && bundle.ok && bundle.topic) || topic?.pages;
  const better = bundle && bundle.ok ? bundle.better_page : null;
  const suggested = bundle && bundle.ok ? bundle.suggested_page : null;
  const nothing = bundle && bundle.ok ? bundle.nothing_recommended : null;
  const all = useMemo(
    () => (bundle && bundle.ok ? [...bundle.parts, ...bundle.optional, ...customParts] : []),
    [bundle, customParts],
  );
  const kept = all.filter((p) => choices[p.id]?.on).length;

  const confirm = () =>
    start(async () => {
      if (!bundle || !bundle.ok) return;
      setError(null);
      const r = await confirmTaskAction(clientId, month, assemble(bundle, all, choices));
      if (r.ok) onConfirmed(r.value);
      else setError(r.error);
    });

  const submitReject = () =>
    start(async () => {
      if (!bundle) return;
      setError(null);
      const targetPage = bundle.ok ? bundle.page : (chosen ?? page);
      const draft = bundle.ok ? assemble(bundle, all, choices) : null;
      const targetSearch = draft?.search ?? (bundle.ok ? (bundle.keyword ?? bundle.search) : search);
      const r = await rejectTaskAction(clientId, {
        month,
        kind: "growth_action",
        rule_id: draft?.rule_id ?? "GA",
        search: targetSearch,
        page: targetPage,
        title: draft?.title ?? `Rejected recommendation: ${shortPage(targetPage)} for “${targetSearch}”`,
        why: draft?.why ?? null,
        steps: draft?.steps ?? [],
        parts: draft?.parts ?? [],
        rejection_reason: rejectReason,
        rejection_note: rejectNote.trim() || undefined,
      });
      if (r.ok) {
        onConfirmed(r.value);
        setShowRejectForm(false);
        setRejectNote("");
        setRejectedMessage(
          `Rejected (${r.value.rejection_reason_label ?? rejectReason})${r.value.rejection_note ? `: ${r.value.rejection_note}` : ""}.`,
        );
      } else {
        setError(r.error);
      }
    });

  const addCustomPart = () => {
    const title = customTitle.trim();
    const steps = customStepsText
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!title) return;
    const localId = `CUSTOM-${Date.now()}-${customParts.length + 1}`;
    const newPart: GrowthPart = {
      id: localId,
      name: title,
      title,
      why: "Custom step added during review.",
      steps: steps.length > 0 ? steps : [title],
      evidence: [],
      core: false,
      confirmed_by_rule: false,
      custom: true,
      action_type: "Custom step",
      benefit: "SEO and conversion",
    };
    setCustomParts((prev) => [...prev, newPart]);
    setChoices((prev) => ({
      ...prev,
      [localId]: { on: true, editing: false, text: newPart.steps.join("\n") },
    }));
    setCustomTitle("");
    setCustomStepsText("");
    setShowCustomForm(false);
  };

  const removeCustomPart = (localId: string) => {
    setCustomParts((prev) => prev.filter((p) => p.id !== localId));
    setChoices((prev) => {
      const next = { ...prev };
      delete next[localId];
      return next;
    });
  };

  const set = (id: string, patch: Partial<Choice>) => setChoices((c) => ({ ...c, [id]: { ...c[id], ...patch } }));

  // A plain function, not a component: a component defined here would remount on every keystroke and drop the textarea's focus.
  function renderPart(p: GrowthPart, index: number | null) {
    const c = choices[p.id];
    if (!c) return null;
    const badge = partBadge(p);
    const stepLines = c.text.split("\n").map((s) => s.trim()).filter(Boolean);
    return (
      <li
        key={p.id}
        className={`rounded-xl border p-3.5 ${
          c.on ? "border-[#bfe9e4] bg-[#f8fdfc]" : "border-dashed border-[#d3d7d9] bg-white"
        }`}
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <label className="flex cursor-pointer items-start gap-2 font-semibold text-[#0a0c0f]">
            <input type="checkbox" checked={c.on} onChange={(e) => set(p.id, { on: e.target.checked })} className="mt-1" />
            <span>
              {index != null && c.on ? `${index}. ` : ""}
              {p.id === "MC-1" ? "Rewrite the meta for clicks" : p.name}
            </span>
          </label>
          <div className="flex flex-wrap items-center gap-2">
            {badge ? (
              <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${badge.cls}`}>{badge.label}</span>
            ) : null}
            {c.on ? (
              <button
                type="button"
                onClick={() => set(p.id, { editing: !c.editing })}
                className="cursor-pointer text-xs font-semibold text-[#00857b] hover:underline"
              >
                {c.editing ? "Done editing" : "Edit steps"}
              </button>
            ) : null}
            {p.custom ? (
              <button
                type="button"
                onClick={() => removeCustomPart(p.id)}
                className="cursor-pointer text-xs font-semibold text-[oklch(0.48_0.17_25)] hover:underline"
              >
                Remove
              </button>
            ) : null}
          </div>
        </div>
        {p.action_type || p.scope ? (
          <p className="mt-1 text-xs text-[#7a838c]">
            {[p.action_type, p.scope, p.benefit ? `for ${p.benefit}` : null].filter(Boolean).join(" · ")}
          </p>
        ) : null}
        {p.why ? <p className="mt-1 text-[13px] text-[#4a5560]">{p.why}</p> : null}
        {p.note && (p.scope !== "page-specific" || /template/i.test(p.note)) ? (
          <p className="mt-1 text-xs text-[#4a5560]">Where: {p.note}</p>
        ) : null}
        {c.editing ? (
          <textarea
            value={c.text}
            onChange={(e) => set(p.id, { text: e.target.value })}
            rows={Math.min(14, Math.max(4, c.text.split("\n").length + 1))}
            className="mt-2 w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-sm text-[#171a22] focus:outline-none focus:ring-2 focus:ring-[#00a99d]"
            aria-label={`Steps for ${p.name}`}
          />
        ) : (
          <div className="mt-2.5 space-y-1.5">
            {stepLines.map((s, idx) => (
              <div key={`${p.id}-s-${idx}`} className="flex items-start gap-2.5 text-[13px] text-[#171a22]">
                <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-[#223540] text-[11px] font-bold text-white">
                  {idx + 1}
                </span>
                <span>{s}</span>
              </div>
            ))}
          </div>
        )}
        {p.evidence.length > 0 && !c.editing ? (
          <ul className="mt-2 list-disc pl-5 text-xs text-[#7a838c]">
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
  const bundleChecklist = bundle
    ? bundle.checklist ?? bundle.context?.checklist
    : undefined;
  const bundleStyleNotes = bundle?.context?.style_notes;
  const bundleHistory = bundle?.page_history;
  const bundleRejections = bundle?.prior_rejections;
  const bundleWinners = bundle?.context?.winners;

  return (
    <div className="mt-4 rounded-xl border border-[#ececec] bg-white p-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#00857b]">
          Bundled growth action planner
        </div>
        {bundle?.focus ? (
          <span className="rounded-full bg-[#223540] px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
            Focus: {bundle.focus}
          </span>
        ) : null}
      </div>

      {!topic && !error ? <p className="mt-2 text-[#4a5560]">Loading the search and the page…</p> : null}
      {topic && !topic.keyword ? (
        <p className="mt-2 text-[#4a5560]">{topic.source}, so there is no watchlist topic to bundle around.</p>
      ) : null}

      {topic?.keyword && pages ? (
        <div className="mt-2 text-[13px] text-[#4a5560]">
          {topic.search ? (
            <>
              Search: <strong className="text-[#0a0c0f]">{topic.search}</strong>{" "}
              <span className="text-xs text-[#7a838c]">(selected under watchlist keyword “{topic.keyword}”)</span>.
            </>
          ) : (
            <>
              Watchlist keyword: <strong className="text-[#0a0c0f]">{topic.keyword}</strong>{" "}
              <span className="text-xs text-[#7a838c]">({topic.source})</span>.
              {bundle && bundle.ok ? (
                <>
                  {" "}
                  Search used: <strong className="text-[#0a0c0f]">{bundle.search}</strong>{" "}
                  <span className="text-xs text-[#7a838c]">({bundle.search_source})</span>.
                </>
              ) : null}
            </>
          )}{" "}
          Page: <strong className="text-[#0a0c0f]">{shortPage(chosen ?? page)}</strong>
          {chosen && chosen !== page ? <span className="text-xs text-[#7a838c]"> (switched from {shortPage(page)})</span> : null}.{" "}
          {better ? (
            <span className="mt-2 block rounded-[10px] border border-[oklch(0.88_0.08_85)] bg-[oklch(0.97_0.045_85)] px-3 py-2 text-xs text-[oklch(0.42_0.1_65)]">
              Another page may serve this search better: <strong>{shortPage(better.url)}</strong>. {better.why}{" "}
              <button type="button" onClick={() => setChosen(better.url)} className="cursor-pointer font-semibold underline">
                Work on that page instead
              </button>
            </span>
          ) : null}
          {suggested ? (
            <span className="mt-2 block rounded-[10px] border border-[oklch(0.88_0.08_85)] bg-[oklch(0.97_0.045_85)] px-3 py-2 text-xs text-[oklch(0.42_0.1_65)]">
              {suggested.url ? <><strong>{shortPage(suggested.url)}</strong>: </> : null}
              {suggested.why} {suggested.next}{" "}
              {suggested.url && pages.pages.some((p) => p.url === suggested.url) ? (
                <button type="button" onClick={() => setChosen(suggested.url!)} className="cursor-pointer font-semibold underline">
                  Review that page
                </button>
              ) : null}
            </span>
          ) : null}
          {pages.pages.length > 1 ? (
            <button type="button" onClick={() => setShowPages((v) => !v)} className="ml-1 cursor-pointer text-xs font-semibold text-[#00857b] hover:underline">
              {showPages ? "Hide the pages" : `Choose a different page (${pages.pages.length})`}
            </button>
          ) : null}
          {showPages ? (
            <>
              <p className="mt-1.5 text-xs text-[#7a838c]">{pages.rule}</p>
              <ul className="mt-2 divide-y divide-[#f1f2f3] rounded-[10px] border border-[#ececec]">
                {(showAll ? pages.pages : [...pages.pages.slice(0, 6), ...pages.pages.slice(6).filter((p) => p.url === page)]).map((p) => (
                  <li key={p.url} className="flex flex-wrap items-center gap-3 px-3 py-2">
                    <input
                      type="radio"
                      name={`pick-${search}-${page}`}
                      checked={chosen === p.url}
                      onChange={() => setChosen(p.url)}
                      aria-label={`Work on ${shortPage(p.url)}`}
                    />
                    <span className="min-w-0 flex-1 break-all font-medium text-[#0a0c0f]">{shortPage(p.url)}</span>
                    {p.fit === "high" ? (
                      <span className="rounded-full bg-[#e9fedc] px-2 py-0.5 text-[10px] font-semibold text-[#2f5a00]" title={p.fit_why}>
                        suits the search
                      </span>
                    ) : null}
                    {p.url === page ? (
                      <span className="rounded-full bg-[#f1f3f4] px-2 py-0.5 text-[10px] font-semibold text-[#4a5560]">selected</span>
                    ) : null}
                    {inPlan(p.url) ? (
                      <span className="rounded-full bg-[#e6f7f5] px-2 py-0.5 text-[10px] font-semibold text-[#00665f]">✓ in plan</span>
                    ) : null}
                    <span className="text-xs tabular-nums text-[#7a838c]">
                      {num(p.impressions)} impr · pos {p.position ?? "–"} ·{" "}
                      {p.title_read === false ? "title not read" : `title ${p.title_says_topic ? "says" : "does not say"} topic`}
                      {p.page_type_name && p.page_type !== "unknown" ? ` · ${p.page_type_name.toLowerCase()}` : ""}
                    </span>
                    {p.fit === "low" ? (
                      <span
                        className="rounded-full bg-[oklch(0.97_0.045_85)] px-2 py-0.5 text-[10px] font-semibold text-[oklch(0.42_0.1_65)]"
                        title={p.fit_why}
                      >
                        does not suit
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
              {pages.pages.length > 6 ? (
                <button type="button" onClick={() => setShowAll((v) => !v)} className="mt-2 cursor-pointer text-xs font-semibold text-[#00857b] hover:underline">
                  {showAll ? "Show fewer pages" : `Show all ${pages.pages.length} pages`}
                </button>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}

      {building ? (
        <p className="mt-3 flex items-center gap-2 text-xs text-[#4a5560]">
          <Spinner />
          Reading {chosen ? shortPage(chosen) : "the page"}…
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="mt-3 rounded-[10px] border border-[oklch(0.88_0.06_25)] bg-[oklch(0.965_0.025_25)] p-3 text-xs text-[oklch(0.48_0.17_25)]">
          {error}
        </p>
      ) : null}
      {rejectedMessage ? (
        <p className="mt-3 rounded-[10px] border border-[oklch(0.88_0.06_25)] bg-[oklch(0.965_0.025_25)] px-3.5 py-2.5 text-xs font-semibold text-[oklch(0.48_0.17_25)]">
          {rejectedMessage}
        </p>
      ) : null}

      {bundle && !bundle.ok ? (
        <div className="mt-3 space-y-3">
          {bundle.context ? <ContextSummary context={bundle.context} focusOrderReason={bundle.focus_order_reason} /> : null}
          <StyleNotesBanner styleNotes={bundleStyleNotes} />
          <PriorRejectionsBanner rejections={bundleRejections} />
          <ChecklistPanel
            checklist={bundleChecklist}
            pageTypeName={bundle.context?.page_type?.name}
            focusOrderReason={bundle.focus_order_reason}
          />
          <PageHistoryPanel history={bundleHistory} />
        </div>
      ) : null}

      {bundle && bundle.ok ? (
        <div className="mt-3 space-y-3 border-t border-[#ececec] pt-3">
          <div>
            <h5 className="font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">
              {nothing ? "Nothing recommended for this page and search" : bundle.draft?.title}
            </h5>
            {nothing ? <p className="mt-1 text-[13px] text-[#4a5560]">{nothing.reason}</p> : null}
          </div>

          {bundle.context ? (
            <ContextSummary
              context={bundle.context}
              focusOrderReason={bundle.focus_order_reason}
              hideQuestions={Boolean(bundleWinners?.comparison.questions)}
            />
          ) : null}

          <StyleNotesBanner styleNotes={bundleStyleNotes} />
          <PriorRejectionsBanner rejections={bundleRejections} />

          {bundleWinners?.comparison.questions ? (
            <div className="rounded-xl border border-[#ececec] bg-[#f8f8f8] p-3.5 text-xs">
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                People Also Ask &amp; searcher questions ({bundleWinners.comparison.questions.checked} checked)
              </div>
              {bundleWinners.comparison.questions.missing.length > 0 ? (
                <ul className="mt-2 space-y-1.5">
                  {bundleWinners.comparison.questions.missing.map((q) => (
                    <li key={q.question} className="rounded-lg border border-[#ececec] bg-white px-3 py-2">
                      <span className="rounded-full bg-[#e6f7f5] px-2 py-0.5 text-[10px] font-semibold text-[#00665f]">
                        {q.source_name}
                      </span>
                      {q.detail ? <span className="ml-2 text-[11px] text-[#7a838c]">{q.detail}</span> : null}
                      <div className="mt-1 font-semibold text-[#0a0c0f]">“{q.question}”</div>
                      {q.why ? <p className="mt-0.5 text-[#4a5560]">{q.why}</p> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-[#00665f]">
                  All {bundleWinners.comparison.questions.checked} checked questions appear to be answered on this page.
                </p>
              )}
            </div>
          ) : null}

          {!nothing ? (
            <p className="text-xs text-[#7a838c]">
              Check what to keep, edit any part&apos;s steps, add custom steps if needed, then confirm or reject with a reason.
            </p>
          ) : null}

          <ul className="space-y-2.5">{bundle.parts.map((p) => renderPart(p, choices[p.id]?.on ? ++number : null))}</ul>

          {bundle.optional.length > 0 ? (
            <div>
              <h5 className="mt-3 text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">Optional: tick to add</h5>
              <ul className="mt-2 space-y-2.5">{bundle.optional.map((p) => renderPart(p, choices[p.id]?.on ? ++number : null))}</ul>
            </div>
          ) : null}

          {customParts.length > 0 ? (
            <div>
              <h5 className="mt-3 text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">Custom steps added</h5>
              <ul className="mt-2 space-y-2.5">{customParts.map((p) => renderPart(p, choices[p.id]?.on ? ++number : null))}</ul>
            </div>
          ) : null}

          {!inPlan(bundle.page) ? (
            <div className="rounded-[10px] border border-dashed border-[#d3d7d9] bg-[#f8f8f8] p-3">
              {!showCustomForm ? (
                <button
                  type="button"
                  onClick={() => setShowCustomForm(true)}
                  className="cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-3.5 py-1 text-xs font-semibold text-[#223540] hover:border-[#00a99d] hover:bg-[#e6f7f5]"
                >
                  + Add custom step
                </button>
              ) : (
                <div className="space-y-2">
                  <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">New custom step</div>
                  <input
                    type="text"
                    value={customTitle}
                    onChange={(e) => setCustomTitle(e.target.value)}
                    placeholder="Step title (e.g. Add pricing comparison table)"
                    aria-label="Custom step title"
                    className="w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-sm text-[#171a22] placeholder:text-[#7a838c]"
                  />
                  <textarea
                    value={customStepsText}
                    onChange={(e) => setCustomStepsText(e.target.value)}
                    rows={3}
                    placeholder="Instructions (one step per line)"
                    aria-label="Custom step instructions"
                    className="w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-sm text-[#171a22] placeholder:text-[#7a838c]"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={addCustomPart}
                      disabled={!customTitle.trim()}
                      className="cursor-pointer rounded-full bg-[#223540] px-3.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      Save custom step
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowCustomForm(false)}
                      className="cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-3.5 py-1.5 text-xs font-semibold text-[#4a5560]"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : null}

          {bundle.left_out.length > 0 ? (
            <p className="text-xs text-[#7a838c]">
              Not in this action: {bundle.left_out.map((l) => `${l.name} (${l.reason})`).join(" · ")}
            </p>
          ) : null}

          <ChecklistPanel
            checklist={bundleChecklist}
            pageTypeName={bundle.context?.page_type?.name}
            focusOrderReason={bundle.focus_order_reason}
          />

          <PageHistoryPanel history={bundleHistory} />

          <div className="flex flex-wrap items-center gap-3 pt-1">
            {inPlan(bundle.page) ? (
              <span className="rounded-full bg-[#e6f7f5] px-3.5 py-1.5 text-xs font-semibold text-[#00665f]">
                ✓ This page is already in the plan.
              </span>
            ) : (
              <>
                {nothing && customParts.length === 0 ? null : (
                  <button
                    type="button"
                    onClick={confirm}
                    disabled={pending || kept === 0}
                    className="cursor-pointer rounded-full bg-[#223540] px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-[#00a99d] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {pending ? (
                      <>
                        <Spinner />
                        Adding…
                      </>
                    ) : (
                      `Confirm as a growth action (${kept} part${kept === 1 ? "" : "s"})`
                    )}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setShowRejectForm((v) => !v)}
                  className="cursor-pointer rounded-full border border-[oklch(0.88_0.06_25)] bg-white px-3.5 py-2 text-xs font-semibold text-[oklch(0.48_0.17_25)] hover:bg-[oklch(0.965_0.025_25)]"
                >
                  {showRejectForm ? "Close rejection" : "Reject recommendation"}
                </button>
              </>
            )}
          </div>

          {!inPlan(bundle.page) && kept === 0 && !nothing ? (
            <p className="text-xs text-[#7a838c]">
              Nothing here to confirm: tick at least one part or add a custom step above.
            </p>
          ) : null}

          {showRejectForm && !inPlan(bundle.page) ? (
            <div className="rounded-xl border border-[oklch(0.88_0.06_25)] bg-[oklch(0.965_0.025_25)] p-3.5 text-xs">
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[oklch(0.48_0.17_25)]">
                Why are you rejecting this recommendation?
              </div>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                <label className="block">
                  <span className="font-semibold text-[#171a22]">Rejection reason</span>
                  <select
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    className="mt-1 w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-xs text-[#171a22]"
                  >
                    {reasons.map((r) => (
                      <option key={r.key} value={r.key}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="font-semibold text-[#171a22]">Reviewer note (optional)</span>
                  <input
                    type="text"
                    value={rejectNote}
                    onChange={(e) => setRejectNote(e.target.value)}
                    placeholder="Brief context for future runs…"
                    className="mt-1 w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-xs text-[#171a22] placeholder:text-[#7a838c]"
                  />
                </label>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={pending}
                  onClick={submitReject}
                  className="cursor-pointer rounded-full bg-[oklch(0.48_0.17_25)] px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {pending ? "Saving rejection…" : "Submit rejection"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowRejectForm(false)}
                  className="cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-3.5 py-1.5 text-xs font-semibold text-[#4a5560]"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
