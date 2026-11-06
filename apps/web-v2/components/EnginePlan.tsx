"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, useTransition } from "react";

import { sendTaskAction, taskTextAction, updateTaskAction } from "@/app/(app)/[clientSlug]/engine/actions";
import { monthLabel } from "@/lib/focus";
import type { Allowance, EngineTask, TaskPart, TaskPlan } from "@/lib/engine";
import { Spinner } from "@/components/ui/Spinner";

const STATUS_STYLE: Record<string, string> = {
  confirmed: "bg-[var(--bg)] text-[var(--text-secondary)]",
  sent: "bg-blue-50 text-blue-800",
  shipped: "bg-green-50 text-green-800",
};

/** A growth action's steps come under "# " headings (its parts); any other task's steps are a plain list. */
function Steps({ steps, grouped }: { steps: string[]; grouped: boolean }) {
  if (!grouped) {
    return (
      <ol className="list-decimal space-y-1 pl-5">
        {steps.map((step, i) => (
          <li key={i}>{step}</li>
        ))}
      </ol>
    );
  }
  return (
    <div className="space-y-3">
      {steps.map((step, i) =>
        step.startsWith("# ") ? (
          <div key={i} className="font-medium text-[var(--text-primary)]">
            {step.slice(2)}
          </div>
        ) : (
          <div key={i} className="flex gap-2 pl-3">
            <span aria-hidden className="text-[var(--text-secondary)]">☐</span>
            <span>{step}</span>
          </div>
        ),
      )}
    </div>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">{label}</div>
      <div className="mt-1">{children}</div>
    </div>
  );
}

/** Where a part opens its tool: on the page itself, or on the topic for a new page. */
function toolHref(slug: string, part: TaskPart, task: EngineTask): string | null {
  if (!part.tool_path || !part.tool_param) return null;
  const value = part.tool_param === "term" ? task.search : task.page;
  return `/${slug}${part.tool_path}?${part.tool_param}=${encodeURIComponent(value)}${part.tool_kind ? `&kind=${part.tool_kind}` : ""}&from=plan`;
}

/** Each part of the action and the tool that carries it out; a part no tool covers is a plain step. */
function Parts({ task }: { task: EngineTask }) {
  const { clientSlug } = useParams<{ clientSlug: string }>();
  const parts = task.parts ?? [];
  if (parts.length === 0) return null;
  return (
    <Detail label="Do it in">
      <ul className="divide-y divide-[var(--border)] rounded-lg border border-[var(--border)] bg-[var(--surface)]">
        {parts.map((part, i) => {
          const href = toolHref(clientSlug, part, task);
          return (
            <li key={`${part.id}-${i}`} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
              <span className="font-medium text-[var(--text-primary)]">{i + 1}. {part.name}</span>
              {href ? (
                <span className="flex items-center gap-2">
                  <span className="text-xs text-[var(--text-tertiary)]">{part.tool_label}</span>
                  <Link href={href} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1 text-xs font-semibold text-[var(--brand-teal)] hover:underline">
                    {part.tool_verb}
                  </Link>
                </span>
              ) : (
                <span className="text-xs text-[var(--text-tertiary)]">No tool for this one yet: it is a step to do by hand</span>
              )}
            </li>
          );
        })}
      </ul>
    </Detail>
  );
}

/** What was confirmed, in full: the same words that go to Teamwork, readable here at any time, before or after it is sent. */
function TaskDetails({ task }: { task: EngineTask }) {
  const measured = [task.metric ? `Measured on ${task.metric}` : null, task.check_on ? `checked ${task.check_on}` : null].filter(Boolean).join(", ");
  return (
    <div className="mt-3 space-y-4 rounded-lg border border-[var(--border)] bg-[var(--bg)] p-4 text-sm text-[var(--text-secondary)]">
      <Detail label="Page">
        <a href={task.page} target="_blank" rel="noreferrer" className="break-all text-[var(--brand-teal)] hover:underline">
          {task.page}
        </a>
      </Detail>
      {task.why ? <Detail label="Why this page">{task.why}</Detail> : null}
      {task.kind === "growth_action" ? <Parts task={task} /> : null}
      {task.steps.length > 0 ? (
        <Detail label={task.kind === "growth_action" ? "The parts, and what to do in each" : "Steps"}>
          <Steps steps={task.steps} grouped={task.kind === "growth_action"} />
        </Detail>
      ) : null}
      {task.done_when ? <Detail label="Done when">{task.done_when}</Detail> : null}
      {measured || task.effort_min ? (
        <Detail label="Measured and sized">
          {[measured, task.effort_min ? `Estimated ${task.effort_min} minutes` : null].filter(Boolean).join(" · ")}
        </Detail>
      ) : null}
      {task.evidence.length > 0 ? (
        <Detail label="Evidence and limitations">
          <ul className="list-disc space-y-1 pl-5">
            {task.evidence.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </Detail>
      ) : null}
      <Detail label="Where it stands">
        Confirmed by {task.confirmed_by}
        {task.teamwork_task_url ? (
          <>
            {" · "}
            <a href={task.teamwork_task_url} target="_blank" rel="noreferrer" className="text-[var(--brand-teal)] hover:underline">
              In Teamwork
            </a>
            {task.teamwork_subtasks ? ` with ${task.teamwork_subtasks} subtask${task.teamwork_subtasks === 1 ? "" : "s"}` : ""}
          </>
        ) : (
          " · not sent to Teamwork yet"
        )}
        {task.shipped_at ? ` · shipped ${task.shipped_at.slice(0, 10)}` : ""}
      </Detail>
    </div>
  );
}

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
  const [open, setOpen] = useState(false);

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
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              aria-label={`${open ? "Hide" : "Show"} the details of ${task.title}`}
              className="mr-1 inline-flex align-middle text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              <ChevronRight size={16} aria-hidden className={`transition-transform ${open ? "rotate-90" : ""}`} />
            </button>
            <button type="button" onClick={() => setOpen((o) => !o)} className="text-left hover:underline">
              {task.title}
            </button>
            {task.kind === "growth_action" ? (
              <span className="ml-2 rounded bg-green-50 px-1.5 py-0.5 text-xs font-semibold text-green-800">growth action</span>
            ) : task.kind === "suggestion" ? (
              <span className="ml-2 rounded bg-amber-50 px-1.5 py-0.5 text-xs font-semibold text-amber-800">confirmed by {task.confirmed_by.split("@")[0]}</span>
            ) : null}
          </div>
          <div className="mt-0.5 truncate text-xs text-[var(--text-secondary)]" title={task.page}>
            “{task.search}” · {shortPage(task.page)}
          </div>
          {task.status === "shipped" && task.check_on ? (
            <div className="mt-0.5 text-xs text-[var(--text-tertiary)]">
              Shipped; its result shows on the monthly review from {new Date(`${task.check_on}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" })}.
            </div>
          ) : null}
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
            {pending ? <><Spinner />Sending…</> : "Send to Teamwork"}
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
      {open ? <TaskDetails task={task} /> : null}
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
