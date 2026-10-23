"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { savePlanReviewAction } from "@/app/(app)/[clientSlug]/decision-engine/actions";
import {
  ACTION_FAMILIES,
  actionDisplayTitle,
  planDraftKey,
  actionCount,
  selectedAction,
  toggleAction,
  type Brief,
  type PlanReview,
} from "@/lib/plan-review";
import "./MonthlyFlow.css";
import { usePlanState } from "./PlanReviewState";

const inputClass =
  "w-full rounded-md border border-[var(--border)] bg-[var(--surface)] p-2 text-sm";
const buttonClass =
  "rounded-md border border-[var(--border)] px-3 py-2 text-sm disabled:opacity-50";

export function PlanReviewPanel({
  initial,
  clientId,
  slug,
  month,
  lockedUids = [],
}: {
  initial: PlanReview;
  clientId: string;
  slug: string;
  month: string;
  lockedUids?: string[];
}) {
  const [stage, setStage] = useState(2);
  const [editingApproved, setEditingApproved] = useState(false);
  const initialReview = {
    ...initial,
    focus: initial.focus || (["visibility", "traffic", "leads"].includes(initial.suggested_focus) ? initial.suggested_focus : ""),
  };
  const [review, setReview] = useState(initialReview);
  const [dirty, setDirty] = useState(false);
  const planState = usePlanState();
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  const draftKey = planDraftKey(clientId, month, initial);
  const noticeKey = `plan-notice:${clientId}:${month}:${initial.assessment_id}:${initial.revision}`;
  const [restoredDraft, setRestoredDraft] = useState(false);
  useEffect(() => {
    const restoreNotice = () => {
      try {
        const notice = sessionStorage.getItem(noticeKey);
        if (notice) setMessage(notice);
      } catch {}
    };
    // A save can refresh the server revision before its action result arrives.
    // Read on mount and on delivery so either ordering retains the warning.
    restoreNotice();
    window.addEventListener("plan-review-notice", restoreNotice);
    return () => window.removeEventListener("plan-review-notice", restoreNotice);
  }, [noticeKey]);
  useEffect(() => {
    try {
      const draft = JSON.parse(sessionStorage.getItem(draftKey) ?? "null");
      if (
        draft &&
        Array.isArray(draft.items) &&
        draft.revision === initial.revision
      ) {
        // A recreated assessment must not recover a pre-reset browser draft.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setReview({ ...initialReview, ...draft });
        setDirty(true);
        planState.setDirty(true);
        setRestoredDraft(true);
      }
    } catch {
      /* Storage may be unavailable; explicit Save remains available. */
    }
    // A new server revision remounts this panel, preventing stale draft replay.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftKey]);
  useEffect(() => {
    if (!dirty) return;
    try {
      sessionStorage.setItem(draftKey, JSON.stringify(review));
    } catch {
      /* explicit Save remains available */
    }
    const prevent = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [review, dirty, draftKey]);
  const update = (patch: Partial<PlanReview>) => {
    setReview((r) => ({ ...r, ...patch }));
    setDirty(true);
    planState.setDirty(true);
    setMessage(null);
  };
  const edit = (index: number, patch: Partial<Brief>) =>
    update({
      items: review.items.map((item, i) =>
        i === index ? { ...item, ...patch } : item,
      ),
    });
  const select = (group: Brief, step: string, index: number) => {
    const current = selectedAction(review.items, group, step);
    if (current && lockedUids.includes(current.action_uid)) return;
    if (!current && actionCount(review.items) >= review.capacity) return;
    const items = toggleAction(review.items, group, step, index, lockedUids);
    update({ items });
    setMessage(
      `${actionCount(items)} growth action${actionCount(items) === 1 ? "" : "s"} selected. Review and approve this selection when ready.`,
    );
  };
  const add = (item: Brief) => {
    update({ items: [...review.items, item] });
    setStage(3);
  };
  const manual = () =>
    add({
      action_uid: `manual-${crypto.randomUUID()}`,
      id: "MANUAL",
      family: "priority_page",
      title: "Custom growth action",
      branch:
        review.focus === "traffic" || review.focus === "leads"
          ? review.focus
          : "visibility",
      target_url: "",
      term: null,
      why: "",
      done_when: "",
      steps: [""],
      evidence: [],
      finding_ids: [],
      effort_min: 60,
      metric: "Manual verification",
      metric_key: "decision",
      check_after_days: 28,
    });
  const save = (approve: boolean) =>
    startTransition(async () => {
      setMessage(null);
      const result = await savePlanReviewAction(
        clientId,
        slug,
        month,
        review,
        approve,
      );
      if (result.ok) {
        setReview(result.review);
        setDirty(false);
        planState.setDirty(false);
        setMessage(
          result.warning ??
            (approve
              ? "Plan approved. The saved version is ready for assignment and delivery."
              : "Draft saved."),
        );
        try {
          sessionStorage.removeItem(draftKey);
          sessionStorage.removeItem(noticeKey);
          if (result.warning) {
            sessionStorage.setItem(
              `plan-notice:${clientId}:${month}:${result.review.assessment_id}:${result.review.revision}`,
              result.warning,
            );
            window.dispatchEvent(new Event("plan-review-notice"));
          }
        } catch {}
        if (approve && result.review.approved_at && !result.warning) {
          const query = new URLSearchParams(window.location.search);
          query.delete("run");
          router.push(`/${slug}/annotations?${query}`);
        } else router.refresh();
      } else setMessage(result.error);
    });
  const count = actionCount(review.items);
  const readonly = Boolean(review.approved_at && !editingApproved);
  const candidates = review.proposals.flatMap((group) =>
    group.steps.map((step, index) => ({ group, step, index })),
  );
  return (
    <section className="monthlyflow space-y-4" aria-labelledby="review-heading">
      <div className="flex flex-wrap justify-between gap-4">
        <div>
          <h2 id="review-heading" className="text-xl font-bold">
            2. Select this month’s growth actions
          </h2>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            Each selection is one growth action. See the page finding,
            recommended change and result to check together.
          </p>
        </div>
        <p className="text-sm">
          {readonly
            ? `Approved version ${review.revision}`
            : dirty
              ? "Unsaved selection"
              : "Draft"}
        </p>
      </div>
      {restoredDraft && dirty && (
        <p role="status" className="text-sm">
          Your selection was restored from this browser tab. Save it to share
          with the team.
        </p>
      )}
      {message && (
        <p
          role="status"
          className="rounded-lg border border-[var(--brand-teal)] p-3 text-sm"
        >
          {message}
        </p>
      )}
      {review.crawl_evidence_limit && (
        <p className="rounded-lg bg-[var(--surface-muted)] p-4 text-sm">
          {review.crawl_evidence_limit}
        </p>
      )}
      <div className="growthworkspace">
        <div>
          <label className="flex max-w-md items-center gap-3 text-sm">
            This month’s focus
            <select
              aria-label="This month’s focus"
              className={inputClass}
              value={review.focus}
              disabled={readonly || pending}
              onChange={(e) => update({ focus: e.target.value })}
            >
              <option value="">Choose a focus</option>
              {[
                ["visibility", "Visibility"],
                ["traffic", "Traffic"],
                ["leads", "Leads"],
                ["continue_strategy", "Continue strategy"],
                ["insufficient_evidence", "Insufficient evidence"],
              ].map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {stage !== 3 &&
            candidates.map(({ group, step, index }) => {
              const selected = selectedAction(review.items, group, step);
              const item =
                group.interventions?.find(
                  (i) => i.steps.length === 1 && i.steps[0] === step,
                ) ?? group;
              const reasoning = item.reasoning;
              const supported = reasoning?.status === "supported";
              const locked = Boolean(
                selected && lockedUids.includes(selected.action_uid),
              );
              return (
                <article
                  className={`growthcard bg-[var(--surface)] ${selected ? "selected" : ""}`}
                  key={`${group.action_uid}-${index}`}
                >
                  <label className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      aria-label={`Select growth action: ${step}`}
                      className="mt-1 h-5 w-5 accent-[var(--brand-teal)]"
                      checked={Boolean(selected)}
                      disabled={
                        pending ||
                        readonly ||
                        locked ||
                        (!selected && (count >= review.capacity || !supported))
                      }
                      onChange={() => select(group, step, index)}
                    />
                    <span>
                      <span className="text-xs text-[var(--brand-teal)]">
                        {ACTION_FAMILIES[group.family] ?? group.family}
                      </span>
                      <strong className="mt-1 block">
                        {actionDisplayTitle(item)}
                      </strong>
                      <span className="mt-2 block break-all text-xs text-[var(--text-secondary)]">
                        {item.target_url}
                      </span>
                    </span>
                  </label>
                  <div className="pl-8">
                    <h4>Finding on this page</h4>
                    {supported ? (
                      reasoning.findings.map((f, i) => (
                        <div key={`${f.uid}-${i}`}>
                          <p>{f.observation}</p>
                          <ul className="mt-2 list-disc pl-4 text-xs text-[var(--text-secondary)]">
                            {f.evidence.map((e, j) => (
                              <li key={j}>{e}</li>
                            ))}
                          </ul>
                        </div>
                      ))
                    ) : (
                      <p>
                        No matching page finding is available. Rerun the
                        assessment before selecting this recommendation.
                      </p>
                    )}
                    <h4>Why this growth action follows</h4>
                    <p>{reasoning?.why_this_action ?? item.why}</p>
                    <h4>Recommended action</h4>
                    <p>{step}</p>
                    <div className="outcome">
                      <strong className="text-sm">Result to check</strong>
                      <p>
                        {reasoning?.outcome ?? item.metric} · check after{" "}
                        {item.check_after_days} days
                      </p>
                    </div>
                    <p className="text-xs text-[var(--text-secondary)]">
                      {reasoning?.limitation}
                    </p>
                    {locked && (
                      <p className="text-sm">
                        Already assigned or delivered. Its approved scope is
                        protected.
                      </p>
                    )}
                  </div>
                </article>
              );
            })}
          {stage !== 3 && !candidates.length && (
            <div className="growthcard">
              <h3 className="font-semibold">
                No supported page fixes available
              </h3>
              <p>
                The engine has not verified a specific page change for this
                assessment. Observations below remain context and do not become
                team assignments.
              </p>
            </div>
          )}
          {stage === 3 && (
            <div className="growthcard">
              <h3 className="text-lg font-bold">
                Review your selected growth actions
              </h3>
              <p>
                These are the same actions you selected. Approval saves this
                selection for Work &amp; Results.
              </p>
              {review.items.map((item, index) => (
                <article
                  key={item.action_uid}
                  className="my-4 border-t border-[var(--border)] pt-4"
                >
                  <h4>
                    {index + 1}. {actionDisplayTitle(item)}
                  </h4>
                  <p className="break-all">
                    {item.target_url || "Choose a target page"}
                  </p>
                  <h4>Linked finding</h4>
                  <p>{item.why}</p>
                  {item.reasoning?.status === "supported" && (
                    <>
                      <h4>Why this growth action follows</h4>
                      <p>{item.reasoning.why_this_action}</p>
                    </>
                  )}
                  <ol className="mt-2 list-decimal pl-5 text-sm">
                    {item.steps.map((step, i) => (
                      <li key={i}>{step}</li>
                    ))}
                  </ol>
                  <p>
                    Result: {item.metric} · {item.check_after_days} days
                  </p>
                  {item.id === "MANUAL" &&
                    !readonly &&
                    !lockedUids.includes(item.action_uid) && (
                      <div className="mt-4 space-y-3">
                        {(
                          [
                            ["title", "Growth action title"],
                            ["target_url", "Target page URL"],
                            ["why", "Why this action"],
                            ["done_when", "Completion criteria"],
                            ["metric", "Result to check"],
                          ] as const
                        ).map(([key, label]) => (
                          <label className="block text-sm" key={key}>
                            {label}
                            <input
                              className={inputClass}
                              value={item[key]}
                              onChange={(e) =>
                                edit(index, { [key]: e.target.value })
                              }
                            />
                          </label>
                        ))}
                        <label className="block text-sm">
                          Specific action
                          <textarea
                            className={inputClass}
                            value={item.steps.join("\n")}
                            onChange={(e) =>
                              edit(index, { steps: e.target.value.split("\n") })
                            }
                          />
                        </label>
                      </div>
                    )}
                </article>
              ))}
              <button className={buttonClass} onClick={() => setStage(2)}>
                Back to growth actions
              </button>
            </div>
          )}
          {Boolean(review.review_opportunities?.length) && (
            <section className="mt-8 border-t border-[var(--border)] pt-5">
              <h3 className="font-bold">Other changes observed</h3>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                These changes have no verified page fix yet. They are not
                selectable growth actions or research assignments.
              </p>
              {review.review_opportunities?.map((o) => (
                <article
                  className="my-5 border-l-2 border-[var(--border)] pl-4"
                  key={o.uid}
                >
                  <h4 className="font-semibold">{o.title}</h4>
                  <p className="mt-1 text-sm">{o.summary}</p>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    {o.limitation}
                  </p>
                </article>
              ))}
            </section>
          )}
        </div>
        <aside className="growthplan rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <h3 className="text-lg font-bold">Your plan</h3>
          <p className="my-3 text-xl font-bold">
            {count} / {review.capacity} growth actions
          </p>
          {review.items.map((item) => (
            <div
              className="my-4 border-t border-[var(--border)] pt-3"
              key={item.action_uid}
            >
              <strong className="text-sm">{actionDisplayTitle(item)}</strong>
              <p className="mt-1 break-all text-xs text-[var(--text-secondary)]">
                {item.target_url}
              </p>
              <p className="mt-2 text-xs">
                Finding:{" "}
                {item.reasoning?.findings.map((f) => f.observation).join(" ") ||
                  item.why}
              </p>
              {!readonly && !lockedUids.includes(item.action_uid) && (
                <button
                  className="mt-2 text-sm text-[var(--brand-teal)] underline"
                  onClick={() =>
                    update({
                      items: review.items.filter(
                        (i) => i.action_uid !== item.action_uid,
                      ),
                    })
                  }
                >
                  Remove
                </button>
              )}
            </div>
          ))}
          {readonly ? (
            <button
              className={buttonClass}
              onClick={() => {
                setEditingApproved(true);
                setStage(2);
              }}
            >
              Edit approved plan
            </button>
          ) : (
            <div className="space-y-3">
              <button
                className={`${buttonClass} w-full`}
                disabled={!dirty || pending}
                onClick={() => save(false)}
              >
                Save draft
              </button>
              {stage === 3 ? (
                <button
                  className="btn btn-primary w-full"
                  disabled={
                    pending ||
                    !count ||
                    count > review.capacity ||
                    !review.focus
                  }
                  onClick={() => save(true)}
                >
                  {pending ? "Saving…" : "Approve growth actions"}
                </button>
              ) : (
                <button
                  className="btn btn-primary w-full"
                  disabled={
                    pending ||
                    !count ||
                    count > review.capacity ||
                    !review.focus
                  }
                  onClick={() => setStage(3)}
                >
                  Review selection →
                </button>
              )}
              <button
                className={`${buttonClass} w-full`}
                disabled={pending || count >= review.capacity}
                onClick={manual}
              >
                Add custom growth action
              </button>
              {dirty && (
                <button
                  className="text-sm underline"
                  onClick={() => {
                    sessionStorage.removeItem(draftKey);
                    setReview(initialReview);
                    setDirty(false);
                    planState.setDirty(false);
                    setRestoredDraft(false);
                  }}
                >
                  Discard changes
                </button>
              )}
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
