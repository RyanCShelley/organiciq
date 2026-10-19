"use client";
import Link from "next/link";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { SlotActionBar } from "@/components/DecisionEngine/SlotActionBar";
import {
  assignSlotAction,
  sendSlotAction,
} from "@/app/(app)/[clientSlug]/decision-engine/actions";
import type { Assignee, RecordAction, SlotState } from "@/lib/monthly-record";
import { runWorkBatch } from "@/lib/work-delivery";
import { actionDisplayTitle } from "@/lib/plan-review";
import type { AnnotationRow } from "@/lib/annotations";
import { AnnotationNote } from "./AnnotationNote";
import { AnnotationsTable } from "./AnnotationsTable";
export type WorkItem = {
  month: string;
  action: RecordAction;
  state?: SlotState;
  teamworkReady: boolean;
  approved: boolean;
};
export function WorkHub({
  items,
  rows,
  assignees,
  clientId,
  slug,
  engineHref,
}: {
  items: WorkItem[];
  rows: AnnotationRow[];
  assignees: Assignee[];
  clientId: string;
  slug: string;
  engineHref: string;
}) {
  const [tab, setTab] = useState("active"),
    [owner, setOwner] = useState(""),
    [due, setDue] = useState("");
  const [selection, setSelection] = useState<string[]>([]),
    [message, setMessage] = useState<string[]>([]);
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  const active = items.filter(
    (row) => !row.state?.shipped_on && row.state?.status !== "skipped",
  );
  const key = (row: WorkItem) => `${row.month}:${row.action.action_uid}`;
  const completed = items.filter((row) => Boolean(row.state?.shipped_on));
  const chosen = active.filter((row) => selection.includes(key(row)));
  const bulk = (send: boolean) =>
    startTransition(async () => {
      const result = await runWorkBatch(
        chosen.map((row) => ({
          key: key(row),
          title: actionDisplayTitle(row.action),
          alreadySent: Boolean(row.state?.sent_at),
          value: row,
        })),
        send,
        async (row) => {
          const input = {
            clientId,
            slug,
            month: row.month,
            uid: row.action.action_uid,
          };
          return send
            ? sendSlotAction(input)
            : assignSlotAction({
                ...input,
                assigneeEmail: owner,
                assigneeName:
                  assignees.find((person) => person.email === owner)?.name ??
                  null,
                due: due || null,
              });
        },
      );
      if (send)
        setSelection((current) =>
          current.filter((value) => !result.deliveredKeys.includes(value)),
        );
      setMessage(result.messages);
      router.refresh();
    });
  return (
    <div className="space-y-5">
      <nav className="flex flex-wrap gap-2" aria-label="Work views">
        {[
          ["active", `Approved / In progress (${active.length})`],
          ["completed", `Completed (${rows.length})`],
          ["results", "Results"],
        ].map(([value, label]) => (
          <button
            key={value}
            className={`btn ${tab === value ? "btn-primary" : "btn-ghost"}`}
            aria-pressed={tab === value}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </nav>
      {message.length > 0 && (
        <ul
          role="status"
          className="rounded-lg border border-[var(--border)] p-3 text-sm"
        >
          {message.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      )}
      {tab === "active" ? (
        <>
          <p className="text-sm text-[var(--text-secondary)]">
            Approved work across all assessment months. Assignment, Teamwork
            delivery and completion are separate steps.
          </p>
          {active.length ? (
            <>
              <div className="flex flex-wrap items-end gap-3 rounded-lg bg-[var(--surface-muted)] p-4">
                <label className="text-sm">
                  Owner
                  <select
                    className="mt-1 block rounded border border-[var(--border)] bg-[var(--surface)] p-2"
                    value={owner}
                    onChange={(e) => setOwner(e.target.value)}
                  >
                    <option value="">Choose owner</option>
                    {assignees.map((person) => (
                      <option key={person.email} value={person.email}>
                        {person.name || person.email}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-sm">
                  Due date
                  <input
                    className="mt-1 block rounded border border-[var(--border)] bg-[var(--surface)] p-2"
                    type="date"
                    value={due}
                    onChange={(e) => setDue(e.target.value)}
                  />
                </label>
                <button
                  className="btn btn-ghost"
                  disabled={
                    pending ||
                    !chosen.length ||
                    !owner ||
                    chosen.some((row) => !row.approved)
                  }
                  onClick={() => bulk(false)}
                >
                  Assign {chosen.length} selected
                </button>
                <button
                  className="btn btn-primary"
                  disabled={
                    pending ||
                    !chosen.length ||
                    chosen.some(
                      (row) =>
                        !row.approved ||
                        !row.teamworkReady ||
                        !row.state?.assignee_email ||
                        !row.state?.due ||
                        row.state?.stale ||
                        Boolean(row.state?.sent_at),
                    )
                  }
                  onClick={() => bulk(true)}
                >
                  Send {chosen.length} selected to Teamwork
                </button>
              </div>
              {active.map((row) => (
                <article
                  key={key(row)}
                  className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5"
                >
                  <div className="flex gap-3">
                    <input
                      type="checkbox"
                      className="mt-1"
                      aria-label={`Select ${row.action.title}`}
                      checked={selection.includes(key(row))}
                      disabled={pending || Boolean(row.state?.sent_at)}
                      onChange={(e) =>
                        setSelection((current) =>
                          e.target.checked
                            ? [...current, key(row)]
                            : current.filter((value) => value !== key(row)),
                        )
                      }
                    />
                    <div className="min-w-0">
                      <h3 className="font-semibold">
                        {actionDisplayTitle(row.action)}
                      </h3>
                      <p className="break-all text-sm text-[var(--text-secondary)]">
                        {row.action.target_url}
                      </p>
                      <p className="text-sm">
                        Assessment {row.month} ·{" "}
                        {row.state?.sent_at
                          ? "Sent to Teamwork"
                          : row.state?.assignee_email
                            ? "Assigned · not sent"
                            : "Approved · awaiting assignment"}
                      </p>
                    </div>
                  </div>
                  <details className="my-3 text-sm">
                    <summary className="cursor-pointer">
                      Evidence & task details
                    </summary>
                    <p>{row.action.why}</p>
                    <ol className="list-decimal pl-5">
                      {row.action.steps?.map((step, i) => (
                        <li key={i}>{step}</li>
                      ))}
                    </ol>
                    <p>Outcome: {row.action.metric}</p>
                    <ul>
                      {row.action.evidence?.map((line, i) => (
                        <li key={i}>{line}</li>
                      ))}
                    </ul>
                  </details>
                  <SlotActionBar
                    key={`${key(row)}:${row.state?.assignee_email}:${row.state?.due}:${row.state?.sent_at}`}
                    action={row.action}
                    state={row.state}
                    assignees={assignees}
                    clientId={clientId}
                    slug={slug}
                    month={row.month}
                    teamworkReady={row.teamworkReady}
                    approved={row.approved}
                  />
                </article>
              ))}
            </>
          ) : (
            <div className="rounded-xl border border-[var(--border)] p-6">
              <p>No approved work waiting for execution.</p>
              <Link
                href={engineHref}
                className="mt-3 inline-block text-[var(--brand-teal)] underline"
              >
                Review recommendations →
              </Link>
              <p className="mt-2 text-sm">
                You can also log completed work below.
              </p>
            </div>
          )}
        </>
      ) : (
        <>
          <p className="text-sm text-[var(--text-secondary)]">
            {tab === "completed"
              ? "What changed and when. Expand measurement details when needed."
              : "Observed results after the recorded measurement window. Changes do not prove causation."}
          </p>
          {tab === "results" &&
            completed.map((row) => {
              const check = new Date(`${row.state!.shipped_on}T12:00:00Z`);
              check.setUTCDate(
                check.getUTCDate() + (row.action.check_after_days || 28),
              );
              const due = check.toISOString().slice(0, 10),
                today = new Date().toLocaleDateString("en-CA", {
                  timeZone: "America/New_York",
                });
              const annotation = rows.find(
                (item) => item.engine_uid === row.action.action_uid,
              );
              const manual = row.action.metric_key === "decision",
                measured = row.state?.result && row.state.result !== "waiting";
              return (
                <article
                  key={key(row)}
                  className="rounded-xl border border-[var(--border)] p-5"
                >
                  <h3 className="font-semibold">
                    {actionDisplayTitle(row.action)}
                  </h3>
                  <p className="text-sm">
                    Primary outcome: {row.action.metric}
                  </p>
                  <p className="mt-2 text-sm">
                    {manual
                      ? "Manual verification required · record the outcome in the completed-work notes"
                      : measured
                        ? `${row.state?.before_value ?? "Unavailable"} → ${row.state?.after_value ?? "Unavailable"} · ${row.state?.result?.replaceAll("_", " ")}`
                        : today < due
                          ? `Waiting for the measurement window through ${due}`
                          : "Waiting for complete source data and the scheduled result check"}
                  </p>
                  {annotation && (
                    <AnnotationNote
                      clientId={clientId}
                      id={annotation.id}
                      notes={annotation.notes}
                    />
                  )}
                </article>
              );
            })}
          {(tab !== "results" ||
            rows.some((row) => !row.engine_uid) ||
            !completed.length) && (
            <AnnotationsTable
              rows={
                tab === "results" ? rows.filter((row) => !row.engine_uid) : rows
              }
              clientId={clientId}
              results={tab === "results"}
            />
          )}
        </>
      )}
    </div>
  );
}
