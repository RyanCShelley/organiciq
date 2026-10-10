"use client";

import { useState, useTransition } from "react";

import {
  assignSlotAction,
  sendSlotAction,
  skipSlotAction,
} from "@/app/(app)/[clientSlug]/decision-engine/actions";
import type { Assignee, RecordAction, SlotState } from "@/lib/monthly-record";

const BUTTON =
  "inline-flex min-h-[34px] items-center rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-[12.5px] font-semibold text-[var(--text-primary)] disabled:opacity-60";
const FIELD =
  "min-h-[34px] rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-[12.5px] text-[var(--text-primary)]";

function who(assignees: Assignee[], id: string | null): string {
  const found = assignees.find((a) => a.user_id === id);
  return found ? found.name || found.email : "somebody";
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
}: {
  action: RecordAction;
  state: SlotState | undefined;
  assignees: Assignee[];
  clientId: string;
  slug: string;
  month: string;
  teamworkReady: boolean;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [askingSkip, setAskingSkip] = useState(false);
  const [reason, setReason] = useState("");

  const [assignee, setAssignee] = useState(state?.assignee_user_id ?? "");
  const [due, setDue] = useState(state?.due ?? "");

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
    run(() =>
      assignSlotAction({
        clientId,
        slug,
        month,
        uid: action.action_uid,
        assigneeUserId: nextAssignee || null,
        due: nextDue || null,
      }),
    );
  }

  /** What would go into Teamwork, for the days the API is not wired up. */
  function copyTask() {
    const lines = [
      action.title,
      "",
      `Page: ${action.target_url}`,
      "",
      "Why this page",
      action.why,
      "",
      "Done when",
      action.done_when,
      "",
      `Measured on ${action.metric}, checked ${action.check_on}`,
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
          Assign slot {action.slot}
        </label>
        <select
          id={`assignee-${action.action_uid}`}
          className={FIELD}
          value={assignee}
          disabled={pending}
          onChange={(e) => {
            setAssignee(e.target.value);
            saveAssignment(e.target.value, due);
          }}
        >
          <option value="">Unassigned</option>
          {assignees.map((person) => (
            <option key={person.user_id} value={person.user_id}>
              {person.name || person.email}
            </option>
          ))}
        </select>

        <label className="sr-only" htmlFor={`due-${action.action_uid}`}>
          Due date for slot {action.slot}
        </label>
        <input
          id={`due-${action.action_uid}`}
          type="date"
          className={FIELD}
          value={due}
          disabled={pending}
          onChange={(e) => {
            setDue(e.target.value);
            saveAssignment(assignee, e.target.value);
          }}
        />

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
            disabled={pending}
            onClick={() =>
              run(() => sendSlotAction({ clientId, slug, month, uid: action.action_uid }))
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
