"use client";

import { useState, useTransition } from "react";

import { sendTaskAction, taskTextAction, updateTaskAction } from "@/app/(app)/[clientSlug]/engine/actions";
import { monthLabel } from "@/lib/focus";
import type { Allowance, EngineTask, TaskPlan } from "@/lib/engine";

const STATUS_STYLE: Record<string, string> = {
  confirmed: "bg-[var(--bg)] text-[var(--text-secondary)]",
  sent: "bg-blue-50 text-blue-800",
  shipped: "bg-green-50 text-green-800",
};

function shortPage(url: string): string {
  return url.replace(/^https?:\/\/[^/]+/, "") || "/";
}

function TaskRow({
  clientId,
  task,
  team,
  teamwork,
  onChange,
}: {
  clientId: string;
  task: EngineTask;
  team: { email: string; name: string | null }[];
  teamwork: TaskPlan["teamwork"];
  onChange: (task: EngineTask) => void;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  function run(task_: () => Promise<{ ok: true; value: EngineTask } | { ok: false; error: string }>) {
    setError(null);
    startTransition(async () => {
      const result = await task_();
      if (result.ok) onChange(result.value);
      else setError(result.error);
    });
  }

  return (
    <li className="py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-medium">
            <span className="mr-2 text-xs text-[var(--text-tertiary)]">{task.rule_id}</span>
            {task.title}
            {task.kind === "suggestion" ? (
              <span className="ml-2 rounded bg-amber-50 px-1.5 py-0.5 text-xs font-semibold text-amber-800">confirmed by {task.confirmed_by.split("@")[0]}</span>
            ) : null}
          </div>
          <div className="mt-0.5 truncate text-xs text-[var(--text-secondary)]" title={task.page}>
            “{task.search}” · {shortPage(task.page)}
          </div>
        </div>
        <span className={`whitespace-nowrap rounded px-2 py-0.5 text-xs font-semibold ${STATUS_STYLE[task.status] ?? STATUS_STYLE.confirmed}`}>
          {task.status}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        {team.length > 0 ? (
          <select
            value={task.assignee_email ?? ""}
            disabled={pending || task.status === "shipped"}
            onChange={(e) =>
              run(() =>
                updateTaskAction(clientId, task.id, e.target.value ? { assignee_email: e.target.value } : { clear_assignee: true }),
              )
            }
            aria-label="Assignee"
            className="rounded-lg border border-[var(--border)] bg-white px-2 py-1"
          >
            <option value="">Unassigned</option>
            {team.map((m) => (
              <option key={m.email} value={m.email}>
                {m.name || m.email}
              </option>
            ))}
          </select>
        ) : null}
        <input
          type="date"
          value={task.due ?? ""}
          disabled={pending || task.status === "shipped"}
          onChange={(e) => run(() => updateTaskAction(clientId, task.id, e.target.value ? { due: e.target.value } : { clear_due: true }))}
          aria-label="Due date"
          className="rounded-lg border border-[var(--border)] px-2 py-1"
        />

        {task.teamwork_task_url ? (
          <a href={task.teamwork_task_url} target="_blank" rel="noreferrer" className="font-semibold text-[var(--brand-teal)] hover:underline">
            In Teamwork ↗
          </a>
        ) : teamwork.configured && teamwork.tasklist_id ? (
          <button
            type="button"
            disabled={pending}
            onClick={() => run(() => sendTaskAction(clientId, task.id))}
            className="rounded-lg bg-[var(--brand-teal)] px-3 py-1 font-semibold text-white disabled:opacity-50"
          >
            {pending ? "Sending…" : "Send to Teamwork"}
          </button>
        ) : (
          <span className="text-[var(--text-tertiary)]">
            {teamwork.configured ? "No Teamwork tasklist for this client" : "Teamwork not set up here"}
          </span>
        )}

        <button
          type="button"
          onClick={async () => {
            const result = await taskTextAction(clientId, task.id);
            if (result.ok) {
              await navigator.clipboard.writeText(result.value);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            } else setError(result.error);
          }}
          className="font-semibold text-[var(--text-secondary)] hover:underline"
        >
          {copied ? "Copied" : "Copy as text"}
        </button>

        {task.status !== "shipped" ? (
          <button
            type="button"
            disabled={pending}
            onClick={() => run(() => updateTaskAction(clientId, task.id, { status: "shipped" }))}
            className="font-semibold text-green-800 hover:underline disabled:opacity-50"
          >
            Mark shipped
          </button>
        ) : null}
        <button
          type="button"
          disabled={pending}
          onClick={() => run(() => updateTaskAction(clientId, task.id, { status: "dropped" }))}
          className="font-semibold text-red-700 hover:underline disabled:opacity-50"
        >
          Drop
        </button>
      </div>
      {error ? (
        <p role="alert" className="mt-2 rounded-lg bg-red-50 p-2 text-xs text-red-800">
          {error}
        </p>
      ) : null}
    </li>
  );
}

export function EnginePlan({
  clientId,
  month,
  tasks,
  allowance,
  teamwork,
  team,
  onTaskChange,
}: {
  clientId: string;
  month: string;
  tasks: EngineTask[];
  allowance: Allowance;
  teamwork: TaskPlan["teamwork"];
  team: { email: string; name: string | null }[];
  onTaskChange: (task: EngineTask) => void;
}) {
  const live = tasks.filter((t) => t.status !== "dropped");
  const pct = allowance.monthly ? Math.min(100, (allowance.used / allowance.monthly) * 100) : 0;

  return (
    <div className="mb-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Plan for {monthLabel(month)}</h2>
        {allowance.monthly != null ? (
          <span className={`text-sm tabular-nums ${allowance.over ? "font-semibold text-amber-800" : "text-[var(--text-secondary)]"}`}>
            {allowance.used} of {allowance.monthly} growth actions
            {allowance.over ? ": over the plan" : ""}
          </span>
        ) : (
          <span className="text-sm text-[var(--text-secondary)]">{allowance.used} confirmed</span>
        )}
      </div>
      {allowance.monthly != null ? (
        <div className="mt-2 h-1.5 rounded bg-[var(--border)]">
          <div className={`h-1.5 rounded ${allowance.over ? "bg-amber-500" : "bg-[var(--brand-teal)]"}`} style={{ width: `${pct}%` }} />
        </div>
      ) : null}

      {live.length === 0 ? (
        <p className="mt-3 text-sm text-[var(--text-secondary)]">
          Nothing confirmed yet. Diagnose a page below and confirm what you want done: it becomes a task here, and from here it goes to Teamwork.
        </p>
      ) : (
        <ul className="mt-2 divide-y divide-[var(--border)] text-sm">
          {live.map((t) => (
            <TaskRow key={t.id} clientId={clientId} task={t} team={team} teamwork={teamwork} onChange={onTaskChange} />
          ))}
        </ul>
      )}
    </div>
  );
}
