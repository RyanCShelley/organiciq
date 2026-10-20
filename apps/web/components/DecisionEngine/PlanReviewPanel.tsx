"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { savePlanReviewAction } from "@/app/(app)/[clientSlug]/decision-engine/actions";
import {
  ACTION_FAMILIES,
  actionDisplayTitle,
  opportunityDraft,
  planDraftKey,
  actionCount,
  selectedAction,
  toggleAction,
  type Brief,
  type PlanReview,
} from "@/lib/plan-review";
import { usePlanState } from "./PlanReviewState";

const inputClass =
  "w-full rounded-md border border-[var(--border)] bg-[var(--surface)] p-2 text-sm";
const shortWhy = (text: string) =>
  text.match(/^.*?[.!?](?=\s+[A-Z]|$)/)?.[0] ?? text;
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
  const [family, setFamily] = useState("all");
  const [review, setReview] = useState(initial);
  const [dirty, setDirty] = useState(false);
  const planState = usePlanState();
  const [changedUid, setChangedUid] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  const draftKey = planDraftKey(clientId, month, initial);
  const [restoredDraft, setRestoredDraft] = useState(false);
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
        setReview({ ...initial, ...draft });
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
    const items = toggleAction(review.items, group, step, index, lockedUids);
    update({ items });
    setChangedUid(null);
    setMessage(
      `${actionCount(items)} actions selected. Review and approve this selection when ready.`,
    );
  };
  const add = (item: Brief) => {
    update({ items: [...review.items, item] });
    setChangedUid(item.action_uid);
    setStage(3);
  };
  const opportunitySelected = (uid: string) =>
    review.items.some((item) =>
      item.flags?.includes(`review-opportunity:${uid}`),
    );
  const manual = () =>
    add({
      action_uid: `manual-${crypto.randomUUID()}`,
      id: "MANUAL",
      family: "investigation",
      title: "Investigate a material change",
      branch: "visibility",
      target_url: "",
      term: null,
      why: "",
      done_when: "",
      steps: [""],
      evidence: [],
      finding_ids: [],
      effort_min: 60,
      metric: "Documented finding and next decision",
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
        } catch {}
        if (approve && result.review.approved_at && !result.warning) {
          const query = new URLSearchParams(window.location.search);
          query.delete("run");
          router.push(`/${slug}/annotations?${query}`);
        } else router.refresh();
      } else setMessage(result.error);
    });
  const move = (index: number, delta: number) => {
    const items = [...review.items];
    [items[index], items[index + delta]] = [items[index + delta], items[index]];
    update({ items });
  };

  return (
    <section
      className="space-y-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6"
      aria-labelledby="review-heading"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="review-heading" className="text-xl font-bold">
          Choose this month’s work
        </h2>
        <p className="text-sm">
          {actionCount(review.items)} / {review.capacity} actions ·{" "}
          {dirty
            ? "Draft changes · save before approval"
            : review.approved_at
              ? `Approved version ${review.revision}`
              : "Draft"}
        </p>
      </div>
      {restoredDraft && dirty && (
        <p role="status" className="text-sm">
          Your draft selection was restored from this browser tab. Save it to
          share with the team.
        </p>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          This month’s focus
          <select
            className={inputClass}
            value={review.focus}
            onChange={(e) => update({ focus: e.target.value })}
          >
            <option value="">Choose after reviewing</option>
            <option value="visibility">Visibility</option>
            <option value="traffic">Traffic</option>
            <option value="leads">Leads</option>
            <option value="continue_strategy">Continue strategy</option>
            <option value="insufficient_evidence">Insufficient evidence</option>
          </select>
        </label>
        <button
          className={buttonClass}
          disabled={pending || !dirty}
          onClick={() => save(false)}
        >
          {pending ? "Saving…" : "Save draft"}
        </button>
        {dirty && (
          <button
            className={buttonClass}
            disabled={pending}
            onClick={() => {
              try {
                sessionStorage.removeItem(draftKey);
              } catch {}
              setReview(initial);
              setDirty(false);
              planState.setDirty(false);
              setRestoredDraft(false);
            }}
          >
            Discard draft changes
          </button>
        )}
        {stage === 3 && (
          <button className={buttonClass} onClick={() => setStage(2)}>
            Back to actions
          </button>
        )}
      </div>
      <details>
        <summary className="cursor-pointer text-sm">
          Client context (optional)
        </summary>
        <textarea
          aria-label="Client context"
          className={inputClass}
          rows={2}
          value={review.strategy}
          onChange={(e) => update({ strategy: e.target.value })}
        />
      </details>
      {message && (
        <p
          role="status"
          className="rounded-lg border border-[var(--brand-teal-deep)] bg-[var(--surface-muted)] p-3 text-sm"
        >
          {message}
        </p>
      )}
      {stage === 1 && (
        <div className="space-y-4">
          <p className="text-sm text-[var(--text-secondary)]">
            After reviewing last month and speaking with the client, decide
            where this month’s work should focus.
          </p>
          <label className="block max-w-md text-sm font-semibold">
            This month’s focus
            <select
              className={inputClass}
              value={review.focus}
              onChange={(e) => {
                const focus = e.target.value;
                update({ focus });
                const next = review.proposals.find(
                  (item) => item.branch === focus,
                );
                if (next) setFamily(next.family);
              }}
            >
              <option value="">Choose after reviewing</option>
              <option value="visibility">Visibility</option>
              <option value="traffic">Traffic</option>
              <option value="leads">Leads</option>
              <option value="continue_strategy">
                Continue current strategy
              </option>
              <option value="insufficient_evidence">
                Insufficient evidence
              </option>
            </select>
          </label>
          <details open={Boolean(review.strategy || review.reason)}>
            <summary className="cursor-pointer text-sm">
              Client context and priorities (optional)
            </summary>
            <label className="mt-2 block text-sm">
              Client strategy and current priorities
              <textarea
                className={inputClass}
                rows={2}
                value={review.strategy}
                onChange={(e) => update({ strategy: e.target.value })}
              />
            </label>
            <label className="mt-2 block text-sm">
              Decision note (optional)
              <textarea
                className={inputClass}
                rows={2}
                value={review.reason}
                onChange={(e) => update({ reason: e.target.value })}
              />
            </label>
          </details>
          <button
            className={`${buttonClass} bg-[var(--brand-teal-deep)] text-white`}
            onClick={() => setStage(2)}
          >
            Choose actions →
          </button>
        </div>
      )}
      {stage === 2 && review.approved_at && !dirty && !editingApproved && (
        <div className="rounded-lg border border-[var(--border)] p-4">
          <h3 className="font-semibold">Approved selection</h3>
          <ul className="my-3 space-y-2">
            {review.items.map((item) => (
              <li key={item.action_uid}>
                <p className="text-sm font-medium">
                  {actionDisplayTitle(item)}
                </p>
                <p className="break-all text-xs text-[var(--text-secondary)]">
                  {item.target_url}
                </p>
              </li>
            ))}
          </ul>
          <p className="text-sm">
            Continue assignment and delivery in Work &amp; Results.
          </p>
          <button
            className={`${buttonClass} mt-3`}
            onClick={() => setEditingApproved(true)}
          >
            Review changes to the selection
          </button>
        </div>
      )}
      {stage === 2 && (!review.approved_at || dirty || editingApproved) && (
        <div className="border-t border-[var(--border)] pt-4">
          {initial.crawl_evidence_limit && (
            <p role="status" className="mb-4 rounded-lg bg-[var(--surface-muted)] p-4 text-sm">
              {initial.crawl_evidence_limit}
            </p>
          )}
          {!!initial.review_opportunities?.length && (
            <section
              className="mb-6 rounded-lg bg-[var(--surface-muted)] p-4"
              aria-label="Review opportunities"
            >
              <h3 className="font-semibold">
                Review opportunities ({initial.review_opportunities.length})
              </h3>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                Observations from the saved {month} assessment, not confirmed
                page defects. They do not count as selected actions. Choose
                whether an investigation is useful before deciding a fix.
              </p>
              <div className="mt-3 grid gap-3 lg:grid-cols-3">
                {initial.review_opportunities.map((opportunity) => (
                  <article
                    key={opportunity.uid}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 text-sm"
                  >
                    <h4 className="font-semibold">{opportunity.title}</h4>
                    <p className="mt-2">{opportunity.summary}</p>
                    <details className="my-3">
                      <summary className="cursor-pointer">
                        Evidence & what to review
                      </summary>
                      <ul className="mt-2 list-disc space-y-1 pl-4">
                        {opportunity.evidence.map((line, i) => (
                          <li key={i}>{line}</li>
                        ))}
                      </ul>
                      <p className="mt-2 font-medium">Why this appeared</p>
                      <p>{opportunity.screening_rule}</p>
                      <p className="mt-2 font-medium">Before choosing work</p>
                      <ul className="list-disc space-y-1 pl-4">
                        {opportunity.review_checks.map((line, i) => (
                          <li key={i}>{line}</li>
                        ))}
                      </ul>
                      <p className="mt-2 text-[var(--text-secondary)]">
                        {opportunity.limitation}
                      </p>
                    </details>
                    <button
                      className={buttonClass}
                      disabled={
                        pending ||
                        opportunitySelected(opportunity.uid) ||
                        actionCount(review.items) >= review.capacity
                      }
                      onClick={() =>
                        add(
                          opportunityDraft(
                            opportunity,
                            `manual-${crypto.randomUUID()}`,
                          ),
                        )
                      }
                    >
                      Draft an investigation
                    </button>
                    <p className="mt-2 text-xs text-[var(--text-secondary)]">
                      {opportunitySelected(opportunity.uid)
                        ? "An investigation for this opportunity is already in your selection."
                        : actionCount(review.items) >= review.capacity
                          ? "The current action allowance is full."
                          : "Adds one local draft action. Confirm a target page and review it before saving or approving."}
                    </p>
                  </article>
                ))}
              </div>
            </section>
          )}
          <h3 className="font-semibold">Choose individual actions</h3>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Select supported actions once. Use the optional filters to narrow
            the list; expand a card for evidence and its checklist.
          </p>
          <div className="my-4 flex flex-wrap gap-2">
            <button
              className={buttonClass}
              aria-pressed={family === "all"}
              onClick={() => setFamily("all")}
            >
              All actions
            </button>
            {Object.entries(ACTION_FAMILIES).map(([key, label]) => {
              const count = review.proposals.filter(
                (item) => item.family === key,
              ).length;
              if (!count) return null;
              return (
                <button
                  key={key}
                  onClick={() => setFamily(key)}
                  aria-pressed={family === key}
                  className={`rounded-lg border p-3 text-left text-sm ${family === key ? "border-[var(--brand-teal-deep)] bg-[var(--surface-muted)] font-semibold" : "border-[var(--border)]"}`}
                >
                  {label}
                  <span className="mt-1 block text-xs font-normal text-[var(--text-secondary)]">
                    {count} page {count === 1 ? "opportunity" : "opportunities"}
                  </span>
                </button>
              );
            })}
          </div>
          {["visibility", "traffic", "leads"].includes(review.focus) &&
            !review.proposals.some((item) => item.branch === review.focus) && (
              <p className="mt-3 text-sm">
                There are no supported {review.focus} actions in this run. You
                can review the other opportunities or add a custom action based
                on the client strategy.
              </p>
            )}
          {review.proposals
            .filter((group) => family === "all" || group.family === family)
            .map((group) => (
              <article
                key={group.action_uid}
                className="mt-3 rounded-lg border border-[var(--border)] p-4"
              >
                <h4 className="text-sm font-semibold">
                  {ACTION_FAMILIES[group.family]}
                </h4>
                <p className="break-all text-sm">{group.target_url}</p>

                <div className="mt-3 space-y-3">
                  {group.steps.map((step, index) => {
                    const selected = selectedAction(review.items, group, step);
                    const locked =
                      selected && lockedUids.includes(selected.action_uid);
                    return (
                      <div
                        key={index}
                        className="flex items-start gap-3 rounded-md bg-[var(--surface-muted)] p-3 text-sm"
                      >
                        <input
                          type="checkbox"
                          aria-label={`Select ${group.title}: ${group.target_url}`}
                          className="mt-1"
                          checked={Boolean(selected)}
                          disabled={pending || Boolean(locked)}
                          onChange={() => select(group, step, index)}
                        />
                        <span className="min-w-0">
                          <strong>
                            {group.interventions?.[index]?.title || group.title}
                          </strong>
                          <span className="mt-1 block text-sm text-[var(--text-secondary)]">
                            {shortWhy(
                              group.interventions?.[index]?.why || group.why,
                            )}
                          </span>
                          <details className="mt-2">
                            <summary className="cursor-pointer text-sm">
                              Checklist & evidence
                            </summary>
                            <p>
                              {group.interventions?.[index]?.why || group.why}
                            </p>
                            <p>{step}</p>
                            <p>
                              Outcome:{" "}
                              {group.interventions?.[index]?.metric ||
                                group.metric}
                            </p>
                            {(
                              group.interventions?.[index]?.evidence ||
                              group.evidence
                            ).map((line, i) => (
                              <p key={i}>{line}</p>
                            ))}
                          </details>
                          {locked && (
                            <span className="block text-xs">
                              Assigned or delivered · protected from scope
                              changes
                            </span>
                          )}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </article>
            ))}
          {!!review.recommendation_limits?.length && (
            <details className="mt-3 text-sm">
              <summary className="cursor-pointer">
                Work withheld from new recommendations (
                {review.recommendation_limits.length})
              </summary>
              <ul className="mt-2 space-y-2">
                {review.recommendation_limits.map((item, i) => (
                  <li key={i}>
                    <strong>{item.title}</strong>
                    <p className="break-all">{item.target_url}</p>
                    <p>{item.reason}</p>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {review.proposals.length === 0 && (
            <p className="mt-2 text-sm">
              No verified page fixes in this run. Review the opportunities above
              when available, or add a custom action below.
            </p>
          )}
          <div className="sticky bottom-3 z-10 mt-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
            <span className="text-sm">
              {actionCount(review.items)} selected · Allowance {review.capacity}
            </span>
            <button className={buttonClass} onClick={manual}>
              Add a custom action
            </button>
            <button
              className={`${buttonClass} bg-[var(--brand-teal-deep)] text-white`}
              onClick={() => setStage(3)}
            >
              Review {actionCount(review.items)} selected actions →
            </button>
          </div>
        </div>
      )}
      {stage === 3 && (
        <div className="space-y-4">
          <h3
            id="selected-plan"
            className="scroll-mt-6 border-t border-[var(--border)] pt-4 font-semibold"
          >
            Selected work · {actionCount(review.items)}{" "}
            {actionCount(review.items) === 1 ? "action" : "actions"}
          </h3>
          <p className="text-sm text-[var(--text-secondary)]">
            This is a summary of the actions checked above. Reorder work if
            needed; approval accepts this selection.
          </p>
          {review.items.length === 0 && (
            <p className="text-sm">
              No actions selected yet. Add a recommendation above or use “Add
              custom action.”
            </p>
          )}
          {review.items.map((item, index) => (
            <details
              open={changedUid === item.action_uid}
              key={item.action_uid}
              className={`rounded-lg border p-4 ${changedUid === item.action_uid ? "border-[var(--brand-teal-deep)] bg-[var(--surface-muted)]" : "border-[var(--border)]"}`}
            >
              <summary className="cursor-pointer font-semibold">
                {index + 1}. {actionDisplayTitle(item)}
                {item.steps.length > 1
                  ? ` · ${item.steps.length} actions in a previously saved bundle`
                  : ""}
              </summary>
              <div className="mt-3 space-y-3">
                <div className="flex flex-wrap gap-2">
                  <button
                    className={buttonClass}
                    disabled={index === 0 || pending}
                    onClick={() => move(index, -1)}
                  >
                    Move up
                  </button>
                  <button
                    className={buttonClass}
                    disabled={index === review.items.length - 1 || pending}
                    onClick={() => move(index, 1)}
                  >
                    Move down
                  </button>
                  <button
                    className={buttonClass}
                    disabled={pending || lockedUids.includes(item.action_uid)}
                    onClick={() =>
                      update({
                        items: review.items.filter((_, i) => i !== index),
                      })
                    }
                  >
                    Remove
                  </button>
                </div>
                {changedUid === item.action_uid && (
                  <p className="text-sm font-semibold">
                    Updated in this draft · {item.steps.length}{" "}
                    {item.steps.length === 1 ? "step" : "steps"} ·{" "}
                    {item.evidence.length} evidence lines
                  </p>
                )}
                <p className="break-all text-sm">
                  {item.target_url ||
                    "Choose the target page below before saving."}
                </p>
                <p className="whitespace-pre-line text-sm">{item.why}</p>
                <ol className="list-decimal space-y-1 pl-5 text-sm">
                  {item.steps.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
                <p className="whitespace-pre-line text-sm">
                  <strong>Done when:</strong> {item.done_when}
                </p>
                <p className="text-sm">
                  <strong>Primary outcome:</strong> {item.metric} · check{" "}
                  {item.check_after_days} days after shipment
                </p>
                <details className="text-sm">
                  <summary className="cursor-pointer">
                    Evidence ({item.evidence.length})
                  </summary>
                  <ul className="mt-2 list-disc pl-5">
                    {item.evidence.map((line, i) => (
                      <li key={i}>{line}</li>
                    ))}
                  </ul>
                </details>
                <details open={changedUid === item.action_uid}>
                  <summary className="cursor-pointer text-sm font-semibold">
                    {item.target_url
                      ? "Edit action details (optional)"
                      : "Choose target page & review action"}
                  </summary>
                  <div className="mt-3 space-y-3">
                    <label className="block text-sm">
                      Action type
                      <select
                        className={inputClass}
                        value={item.family}
                        onChange={(e) =>
                          edit(index, { family: e.target.value })
                        }
                      >
                        {Object.entries(ACTION_FAMILIES).map(([key, label]) => (
                          <option key={key} value={key}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="block text-sm">
                        Brief title
                        <input
                          className={inputClass}
                          value={item.title}
                          onChange={(e) =>
                            edit(index, { title: e.target.value })
                          }
                        />
                      </label>
                      <label className="block text-sm">
                        Target page
                        <input
                          className={inputClass}
                          value={item.target_url}
                          onChange={(e) =>
                            edit(index, { target_url: e.target.value })
                          }
                          placeholder="https://example.com/page"
                        />
                      </label>
                    </div>
                    <label className="block text-sm">
                      Why this work
                      <textarea
                        className={inputClass}
                        rows={2}
                        value={item.why}
                        onChange={(e) => edit(index, { why: e.target.value })}
                      />
                    </label>
                    <label className="block text-sm">
                      Checklist, one step per line
                      <textarea
                        className={inputClass}
                        rows={4}
                        value={item.steps.join("\n")}
                        onChange={(e) =>
                          edit(index, { steps: e.target.value.split("\n") })
                        }
                      />
                    </label>
                    <label className="block text-sm">
                      Done when
                      <textarea
                        className={inputClass}
                        rows={2}
                        value={item.done_when}
                        onChange={(e) =>
                          edit(index, { done_when: e.target.value })
                        }
                      />
                    </label>
                    <label className="block text-sm">
                      Evidence and limitations, one per line
                      <textarea
                        className={inputClass}
                        rows={3}
                        value={item.evidence.join("\n")}
                        onChange={(e) =>
                          edit(index, {
                            evidence: e.target.value
                              .split("\n")
                              .filter(Boolean),
                          })
                        }
                      />
                    </label>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <label className="block text-sm">
                        Outcome to check
                        <input
                          className={inputClass}
                          value={item.metric}
                          onChange={(e) =>
                            edit(index, { metric: e.target.value })
                          }
                        />
                      </label>
                      <label className="block text-sm">
                        Automated measurement
                        <select
                          className={inputClass}
                          value={item.metric_key}
                          onChange={(e) =>
                            edit(index, { metric_key: e.target.value })
                          }
                        >
                          <option value="decision">Manual verification</option>
                          <option value="term_position">Term position</option>
                          <option value="page_clicks">Page clicks</option>
                          <option value="page_impressions">
                            Page impressions
                          </option>
                          <option value="page_position">Page position</option>
                          <option value="engagement_rate">
                            Engagement rate
                          </option>
                          <option value="page_lead_rate">
                            Page-local lead event rate
                          </option>
                          <option value="ai_presence">Site AI presence</option>
                        </select>
                      </label>
                      <label className="block text-sm">
                        Days after shipment
                        <input
                          type="number"
                          min={7}
                          max={180}
                          className={inputClass}
                          value={item.check_after_days}
                          onChange={(e) =>
                            edit(index, {
                              check_after_days: Number(e.target.value),
                            })
                          }
                        />
                      </label>
                    </div>
                  </div>
                </details>
              </div>
            </details>
          ))}
          <button
            className={buttonClass}
            disabled={pending}
            onClick={() => setStage(2)}
          >
            ← Change selected actions
          </button>

          {review.setup_findings.length > 0 && (
            <details>
              <summary className="cursor-pointer font-semibold">
                Page ownership to review · no growth slot used
              </summary>
              {review.setup_findings.map((x, i) => (
                <p className="mt-2 text-sm" key={i}>
                  {x.target_url}: {x.why}
                </p>
              ))}
            </details>
          )}
          <h3 className="border-t border-[var(--border)] pt-4 font-semibold">
            Approve the selected actions
          </h3>
          <p className="text-sm">
            Approval makes this saved selection available in Work & Results.
            Changes after approval create a draft and require approval again.
          </p>
          {actionCount(review.items) > review.capacity && (
            <p role="alert" className="text-sm text-red-700">
              {actionCount(review.items)} actions selected; this plan allows{" "}
              {review.capacity}. Uncheck actions before approving.
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            <button
              className={buttonClass}
              disabled={pending || (!dirty && Boolean(review.approved_at))}
              onClick={() => save(false)}
            >
              Save draft
            </button>
            <button
              className={`${buttonClass} bg-[var(--brand-teal-deep)] text-white`}
              disabled={
                pending ||
                actionCount(review.items) > review.capacity ||
                (!dirty && Boolean(review.approved_at))
              }
              onClick={() => save(true)}
            >
              Approve {actionCount(review.items)}{" "}
              {actionCount(review.items) === 1 ? "action" : "actions"}
            </button>
          </div>
        </div>
      )}
      {review.versions.length > 0 && (
        <details>
          <summary className="cursor-pointer text-sm">
            Approved history ({review.versions.length})
          </summary>
          {review.versions.map((v) => (
            <p className="mt-1 text-sm" key={v.revision}>
              Version {v.revision}
              {v.retired_at ? " · Retired" : ""} · {v.approved_at} ·{" "}
              {v.approved_by}
            </p>
          ))}
        </details>
      )}
    </section>
  );
}
