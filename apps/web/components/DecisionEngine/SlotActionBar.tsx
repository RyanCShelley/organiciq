"use client";

import Link from "next/link";
import { useRef, useState, useTransition } from "react";

import {
  assignSlotAction,
  sendSlotAction,
  shipSlotAction,
  skipSlotAction,
} from "@/app/(app)/[clientSlug]/decision-engine/actions";
import { formatDay, type Assignee, type RecordAction, type SlotState } from "@/lib/monthly-record";

const BUTTON =
  "inline-flex min-h-[34px] items-center rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-[12.5px] font-semibold text-[var(--text-primary)] disabled:opacity-60";
const FIELD =
  "min-h-[34px] rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-[12.5px] text-[var(--text-primary)]";

function who(assignees: Assignee[], email: string | null): string {
  const found = assignees.find((a) => a.email === email);
  return found ? found.name || found.email : email || "somebody";
}

/**
 * Assign, skip, send — the three things that turn a plan into work.
 *
 * Kept out of `SlotCard` so the card stays a server component: the card is
 * what the engine decided, this is what the team does about it, and the two
 * are stored apart for the same reason.
 */
export function SlotActionBar({
  action,
  state,
  assignees,
  clientId,
  slug,
  month,
  teamworkReady,
  approved = true,
  onAssignmentSaved,
}: {
  action: RecordAction;
  state: SlotState | undefined;
  assignees: Assignee[];
  clientId: string;
  slug: string;
  month: string;
  teamworkReady: boolean;
  approved?: boolean;
  onAssignmentSaved?: (due: string) => void;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [askingSkip, setAskingSkip] = useState(false);
  const [reason, setReason] = useState("");
  const [completing, setCompleting] = useState(false);
  const [completionDate, setCompletionDate] = useState(new Date().toLocaleDateString("en-CA", {timeZone:"America/New_York"}));

  const [assignee, setAssignee] = useState(state?.assignee_email ?? "");
  const [due, setDue] = useState(state?.due ?? "");
  const dueField = useRef<HTMLInputElement>(null);
  const [assignmentSaved, setAssignmentSaved] = useState(false);
  const assignmentDirty = assignee !== (state?.assignee_email ?? "") || due !== (state?.due ?? "");
  const shippedOn = state?.shipped_on ?? null;

  const status = state?.status ?? "planned";
  const sentUrl = state?.teamwork_task_url ?? null;

  function run(fn: () => Promise<{ ok: boolean; error?: string }>) {
    setError(null);
    startTransition(async () => {
      const result = await fn();
      if (!result.ok) setError(result.error ?? "That did not save");
    });
  }

  function saveAssignment(nextAssignee: string, nextDue: string) {
    run(async () => {
      const result = await assignSlotAction({
        clientId,
        slug,
        month,
        uid: action.action_uid,
        assigneeEmail: nextAssignee || null,
        assigneeName:
          assignees.find((a) => a.email === nextAssignee)?.name ?? null,
        due: nextDue || null,
      });
      if (result.ok) {
        setAssignmentSaved(true);
        onAssignmentSaved?.(nextDue);
      }
      return result;
    });
  }

  /** What would go into Teamwork, for the days the API is not wired up. */
  function copyTask() {
    const lines = [
      action.title,
      "",
      action.target_url ? `Page: ${action.target_url}` : `New page for: ${action.term ?? action.title}`,
      "",
      "Why this page",
      action.why,
      "",
      "Done when",
      action.done_when,
      "",
      "Checklist",
      ...(action.steps ?? []).map((step, index) => `${index + 1}. ${step}`),
      "",
      "Evidence and limitations",
      ...(action.evidence ?? []),
      "",
      `Measured on ${action.metric}, checked ${action.check_after_days ? `${action.check_after_days} days after shipment` : action.check_on}`,
      `Estimated ${action.effort_min} minutes`,
    ];
    navigator.clipboard.writeText(lines.join("\n")).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      },
      () => setError("The browser would not give access to the clipboard"),
    );
  }

  if (!approved) return <p className="text-sm text-[var(--text-secondary)]">Save and approve the reviewed plan before assigning or delivering growth work.</p>;
  if (status === "skipped") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[12.5px] text-[var(--text-secondary)]">
          <span className="font-semibold text-[var(--text-primary)]">Skipped</span>
          {state?.skip_reason ? ` — ${state.skip_reason}` : null}
        </p>
        <button
          type="button"
          className={BUTTON}
          disabled={pending}
          onClick={() =>
            run(() =>
              skipSlotAction({ clientId, slug, month, uid: action.action_uid, undo: true }),
            )
          }
        >
          Put it back
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* A re-run can reshuffle the slots. The uid is keyed on the slot
          number, so without this the card would show yesterday's assignment
          beside today's different action and say nothing. */}
      {state?.stale ? (
        <p
          role="alert"
          className="rounded-[8px] bg-[#FFF8EE] px-3 py-2 text-[12.5px] text-[#6B3A06]"
        >
          This slot held a different action when it was assigned. Check it before
          sending.
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor={`assignee-${action.action_uid}`}>
          Owner for {action.title}
        </label>
        <select
          id={`assignee-${action.action_uid}`}
          className={FIELD}
          value={assignee}
          disabled={pending}
          onChange={(e) => {
            setAssignee(e.target.value);
            setAssignmentSaved(false);
          }}
        >
          <option value="">Unassigned</option>
          {assignees.map((person) => (
            <option key={person.email} value={person.email}>
              {person.name || person.email}
            </option>
          ))}
          {/* Somebody assigned before they appeared in the list — a left
              colleague, or a Teamwork account that has moved domain. */}
          {assignee && !assignees.some((a) => a.email === assignee) ? (
            <option value={assignee}>{assignee}</option>
          ) : null}
        </select>

        <label className="sr-only" htmlFor={`due-${action.action_uid}`}>
          Due date for {action.title}
        </label>
        <input
          id={`due-${action.action_uid}`}
          type="date"
          className={FIELD}
          ref={dueField}
          defaultValue={state?.due ?? ""}
          disabled={pending}
          onChange={(e) => {
            setDue(e.target.value);
            setAssignmentSaved(false);
          }}
        />

        <button
          type="button"
          className={BUTTON}
          disabled={pending || Boolean(state?.stale)}
          onClick={() => {
            const nextDue = dueField.current?.value ?? "";
            setDue(nextDue);
            saveAssignment(assignee, nextDue);
          }}
        >Save assignment</button>
        {assignmentSaved ? <span role="status">Assignment saved.</span> : assignmentDirty ? <span>Unsaved assignment changes</span> : null}

        {sentUrl ? (
          <a
            href={sentUrl}
            target="_blank"
            rel="noreferrer"
            className={`${BUTTON} no-underline`}
          >
            Open in Teamwork
          </a>
        ) : teamworkReady ? (
          <button
            type="button"
            className={BUTTON}
            disabled={pending || !state?.assignee_email || !state?.due || assignmentDirty || Boolean(state?.stale)}
            onClick={() =>
              run(() => {
                if ((dueField.current?.value ?? "") !== (state?.due ?? "")) {
                  return Promise.resolve({ok: false, error: "Save the assignment changes before sending."});
                }
                return sendSlotAction({ clientId, slug, month, uid: action.action_uid });
              })
            }
          >
            {pending ? "Sending…" : "Send to Teamwork"}
          </button>
        ) : (
          // Teamwork is not wired up for this client yet. Copying the task is
          // what the team does by hand today, so offer that rather than a
          // button that only ever errors.
          <button type="button" className={BUTTON} onClick={copyTask}>
            {copied ? "Copied" : "Copy for Teamwork"}
          </button>
        )}

        {/* Until this is set, every verdict on this action carries "not
            marked done" — and a caveat on every row is one nobody
            reads. */}
        {shippedOn ? (
          <button
            type="button"
            className={BUTTON}
            disabled={pending}
            title="Clear the done date"
            onClick={() =>
              run(() =>
                shipSlotAction({
                  clientId,
                  slug,
                  month,
                  uid: action.action_uid,
                  shippedOn: null,
                }),
              )
            }
          >
            Done {formatDay(shippedOn)}
          </button>
        ) : null}
        {shippedOn ? (
          <Link
            href={`/${slug}/annotations`}
            className="text-[12.5px] text-[var(--brand-teal-hover)] underline"
          >
            In Work & Results
          </Link>
        ) : completing ? (
          <form className="flex flex-wrap items-center gap-2" onSubmit={event=>{event.preventDefault();run(async()=>{const result=await shipSlotAction({clientId,slug,month,uid:action.action_uid,shippedOn:completionDate});if(result.ok)setCompleting(false);return result;});}}>
            <label className="text-sm">Completed on<input required className={FIELD} type="date" value={completionDate} onChange={e=>setCompletionDate(e.target.value)}/></label>
            <button className={BUTTON} disabled={pending} type="submit">Save completion</button><button className={BUTTON} type="button" onClick={()=>setCompleting(false)}>Cancel</button>
          </form>
        ) : <button type="button" className={BUTTON} disabled={pending} onClick={()=>setCompleting(true)}>Mark completed</button>}


        {askingSkip ? null : (
          <button
            type="button"
            className={BUTTON}
            disabled={pending}
            onClick={() => setAskingSkip(true)}
          >
            Skip
          </button>
        )}

        {status === "assigned" && assignee ? (
          <span className="text-[12.5px] text-[var(--text-tertiary)]">
            With {who(assignees, assignee)}
            {state?.sent_at ? " · sent" : ""}
          </span>
        ) : null}
      </div>

      {askingSkip ? (
        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor={`reason-${action.action_uid}`}>
            Why slot {action.slot} is being skipped
          </label>
          <input
            id={`reason-${action.action_uid}`}
            className={`${FIELD} min-w-[280px] flex-1`}
            placeholder="Why skip it? Next month's run reads this."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <button
            type="button"
            className={BUTTON}
            disabled={pending || !reason.trim()}
            onClick={() =>
              run(async () => {
                const result = await skipSlotAction({
                  clientId,
                  slug,
                  month,
                  uid: action.action_uid,
                  reason,
                });
                if (result.ok) setAskingSkip(false);
                return result;
              })
            }
          >
            Skip it
          </button>
          <button
            type="button"
            className={BUTTON}
            onClick={() => {
              setAskingSkip(false);
              setReason("");
            }}
          >
            Cancel
          </button>
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="text-[12px] text-[#B4441C]">
          {error}
        </p>
      ) : null}
    </div>
  );
}
