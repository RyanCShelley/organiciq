"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import {
  checkLiveAction,
  markPartAction,
  sendTaskAction,
  taskTextAction,
  updateTaskAction,
  workAction,
} from "@/app/(app)/[clientSlug]/engine/actions";
import {
  DARK,
  Pill,
  RejectForm,
  StyleNotesBanner,
  TEAL,
  formatDay,
  shortPage,
  toneStyle,
  type Tone,
} from "@/components/engine-workbench/tokens";
import { Spinner } from "@/components/ui/Spinner";
import {
  REJECTION_REASONS,
  type Allowance,
  type EngineTask,
  type MonthWork,
  type RejectionReason,
  type TaskPart,
  type TaskPartInput,
  type TaskPlan,
  type WorkTool,
} from "@/lib/engine";
import { monthLabel } from "@/lib/focus";

const STATUS_TONE: Record<string, Tone> = {
  confirmed: "info",
  sent: "ok",
  shipped: "lime",
  rejected: "miss",
  dropped: "warn",
};

type EditableSection = {
  uid: string;
  id: string;
  name: string;
  status: "open" | "done";
  custom: boolean;
  stepsText: string;
};

function parseGrowthSections(task: EngineTask): EditableSection[] {
  const parts = task.parts ?? [];
  const rawSections: { name: string; lines: string[] }[] = [];
  for (const step of task.steps ?? []) {
    if (step.startsWith("# ")) {
      rawSections.push({ name: step.slice(2).replace(/^\d+\.\s*/, "").trim(), lines: [] });
    } else if (rawSections.length > 0) {
      rawSections[rawSections.length - 1].lines.push(step);
    } else {
      rawSections.push({ name: parts[0]?.name ?? "Task steps", lines: [step] });
    }
  }

  if (parts.length > 0) {
    return parts.map((p, idx) => {
      const matched =
        rawSections[idx] ??
        rawSections.find((s) => s.name.toLowerCase() === p.name.trim().toLowerCase());
      return {
        uid: `${p.id || "part"}-${idx}`,
        id: p.id || (p.custom ? "CUSTOM" : ""),
        name: p.name,
        status: p.status ?? "open",
        custom: Boolean(p.custom || p.id === "CUSTOM"),
        stepsText: matched ? matched.lines.join("\n") : "",
      };
    });
  }

  return rawSections.map((s, idx) => ({
    uid: `sec-${idx}`,
    id: "",
    name: s.name,
    status: "open",
    custom: false,
    stepsText: s.lines.join("\n"),
  }));
}

/** A growth action's steps come under "# " headings (its parts); any other task's steps are a plain list. */
function Steps({ steps, grouped }: { steps: string[]; grouped: boolean }) {
  if (!grouped) {
    return (
      <div className="space-y-2">
        {steps.map((step, i) => (
          <div key={i} className="flex items-start gap-2.5 text-[13px] text-[#171a22]">
            <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-[#223540] text-[11px] font-bold text-white">
              {i + 1}
            </span>
            <span>{step}</span>
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="space-y-2.5">
      {steps.map((step, i) =>
        step.startsWith("# ") ? (
          <div key={i} className="pt-1 font-[var(--font-heading)] text-[13px] font-bold text-[#0a0c0f]">
            {step.slice(2)}
          </div>
        ) : (
          <div key={i} className="flex gap-2 pl-2 text-[13px] text-[#171a22]">
            <span aria-hidden className="text-[#00a99d]">→</span>
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
      <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">{label}</div>
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
function Parts({ task, clientId, onChange }: { task: EngineTask; clientId: string; onChange: (t: EngineTask) => void }) {
  const { clientSlug } = useParams<{ clientSlug: string }>();
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const mark = (index: number, done: boolean) =>
    start(async () => {
      const r = await markPartAction(clientId, task.id, index, done);
      if (r.ok) {
        setError(null);
        onChange(r.value);
      } else setError(r.error);
    });
  const [message, setMessage] = useState<string | null>(null);
  const check = () =>
    start(async () => {
      const r = await checkLiveAction(clientId, task.id);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setError(null);
      onChange(r.value.task);
      const c = r.value.check;
      const tw =
        c.teamwork && c.teamwork.marked
          ? `${c.teamwork.marked} part${c.teamwork.marked === 1 ? "" : "s"} marked done from Teamwork. `
          : c.teamwork?.error
            ? `Teamwork: ${c.teamwork.error} `
            : "";
      setMessage(
        tw +
          (c.unreadable
            ? `Could not read the page, so nothing was judged: ${c.unreadable}`
            : c.live
              ? `${c.live} part${c.live === 1 ? "" : "s"} seen live and marked done.`
              : "Nothing new is live on the page yet."),
      );
    });
  const parts = task.parts ?? [];
  if (parts.length === 0) return null;
  return (
    <Detail label="Do it in">
      <ul className="divide-y divide-[#f1f2f3] rounded-xl border border-[#ececec] bg-white">
        {parts.map((part, i) => {
          const href = toolHref(clientSlug, part, task);
          const isMc1 = part.id === "MC-1";
          const isCustom = Boolean(part.custom || part.id === "CUSTOM");
          const verb = isMc1 ? "Rewrite title & meta" : part.tool_verb;
          return (
            <li key={`${part.id}-${i}`} className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-semibold text-[#0a0c0f]">
                  {i + 1}. {part.name}
                </span>
                {isCustom ? <Pill t="ok">Custom</Pill> : null}
                {isMc1 ? <Pill t="lime">Title &amp; Meta</Pill> : null}
                {part.status === "done" ? (
                  <Pill t="ok">
                    ✓ Done{part.done_at ? ` ${part.done_at.slice(0, 10)}` : ""}
                    {part.done_by ? ` by ${part.done_by}` : ""}
                  </Pill>
                ) : null}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {href ? (
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-[#7a838c]">{part.tool_label}</span>
                    <Link
                      href={href}
                      className="rounded-full border border-[#e3e6e8] bg-white px-3 py-1 text-xs font-semibold text-[#00857b] hover:bg-[#eef8f7]"
                    >
                      {verb}
                    </Link>
                  </span>
                ) : (
                  <span className="text-xs text-[#7a838c]">
                    {isCustom ? "Custom step" : "Step to do by hand"}
                  </span>
                )}

                {part.status === "done" ? (
                  <button
                    type="button"
                    disabled={pending}
                    onClick={() => mark(i, false)}
                    className="cursor-pointer text-xs font-semibold text-[#4a5560] underline disabled:opacity-50"
                  >
                    Not done
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={pending}
                    onClick={() => mark(i, true)}
                    className="cursor-pointer rounded-full bg-[#223540] px-3 py-1 text-xs font-semibold text-white disabled:opacity-50"
                  >
                    Mark done
                  </button>
                )}
              </div>

              {part.verified_how ? (
                <details className="basis-full text-xs text-[#00665f]">
                  <summary className="cursor-pointer font-semibold">✓ Seen live on the page</summary>
                  <p className="mt-1 text-[#4a5560]">{part.verified_how}</p>
                </details>
              ) : part.status === "done" && part.done_how ? (
                <p className="basis-full text-xs text-[#4a5560]">
                  {part.done_how}{" "}
                  {part.last_check?.result === "unreadable"
                    ? "The page could not be read to confirm it."
                    : part.last_check?.result === "not_live"
                      ? "Not seen live on the page yet."
                      : part.last_check?.result === "cannot"
                        ? ""
                        : "The page has not been checked yet."}
                </p>
              ) : part.status !== "done" && part.last_check ? (
                <p
                  className={`basis-full text-xs ${
                    part.last_check.result === "unreadable" ? "text-amber-800" : "text-[#4a5560]"
                  }`}
                >
                  {part.last_check.result === "not_live" ? "Not live yet. " : ""}
                  {part.last_check.note}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
      {error ? (
        <p role="alert" className="mt-2 text-xs text-red-800">
          {error}
        </p>
      ) : null}
      <div className="mt-2.5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={pending}
          onClick={check}
          className="cursor-pointer rounded-full border border-[#e3e6e8] bg-white px-3.5 py-1 text-xs font-semibold text-[#223540] hover:bg-[#f6f7f7] disabled:opacity-50"
        >
          {pending ? (
            <>
              <Spinner />
              Reading the page…
            </>
          ) : (
            "Check Teamwork and the page"
          )}
        </button>
        {message ? <span className="text-xs text-[#4a5560]">{message}</span> : null}
      </div>
      <p className="mt-2 text-xs text-[#7a838c]">
        Marking a part done adds it to{" "}
        <Link href={`/${clientSlug}/annotations`} className="font-semibold text-[#00857b] hover:underline">
          Annotations
        </Link>{" "}
        and starts measuring it. The page is also read once a day: when it shows a part&apos;s change, that part is marked done for you.
      </p>
    </Detail>
  );
}

/** What was confirmed, in full: the same words that go to Teamwork, readable here at any time, before or after it is sent. */
function TaskDetails({ task, clientId, onChange }: { task: EngineTask; clientId: string; onChange: (t: EngineTask) => void }) {
  const [editing, setEditing] = useState(false);
  const [sections, setSections] = useState<EditableSection[]>(() => parseGrowthSections(task));
  const [flatText, setFlatText] = useState(() => (task.steps ?? []).join("\n"));
  const [newCustomName, setNewCustomName] = useState("");
  const [newCustomBody, setNewCustomBody] = useState("");
  const [saving, startSave] = useTransition();
  const [saveError, setSaveError] = useState<string | null>(null);

  const canEdit = task.status !== "shipped" && task.status !== "dropped" && task.status !== "rejected";
  const isGrowth = task.kind === "growth_action";

  function openEditor() {
    setSections(parseGrowthSections(task));
    setFlatText((task.steps ?? []).join("\n"));
    setNewCustomName("");
    setNewCustomBody("");
    setSaveError(null);
    setEditing(true);
  }

  function addCustomSection() {
    const title = newCustomName.trim();
    if (!title) return;
    const lines = newCustomBody
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    const bodyText = lines.length > 0 ? lines.join("\n") : title;
    setSections((prev) => [
      ...prev,
      {
        uid: `custom-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        id: "CUSTOM",
        name: title,
        status: "open",
        custom: true,
        stepsText: bodyText,
      },
    ]);
    setNewCustomName("");
    setNewCustomBody("");
  }

  function saveSteps() {
    setSaveError(null);
    startSave(async () => {
      if (isGrowth) {
        const steps: string[] = [];
        const parts: TaskPartInput[] = [];
        sections.forEach((sec, idx) => {
          steps.push(`# ${idx + 1}. ${sec.name}`);
          steps.push(
            ...sec.stepsText
              .split("\n")
              .map((l) => l.trim())
              .filter(Boolean),
          );
          parts.push({
            id: sec.custom ? "CUSTOM" : sec.id,
            name: sec.name,
            status: sec.status,
            ...(sec.custom ? { custom: true } : {}),
          });
        });
        const r = await updateTaskAction(clientId, task.id, { steps, parts });
        if (r.ok) {
          onChange(r.value);
          setEditing(false);
        } else {
          setSaveError(r.error);
        }
      } else {
        const steps = flatText
          .split("\n")
          .map((l) => l.trim())
          .filter(Boolean);
        const r = await updateTaskAction(clientId, task.id, { steps });
        if (r.ok) {
          onChange(r.value);
          setEditing(false);
        } else {
          setSaveError(r.error);
        }
      }
    });
  }

  const measured = [task.metric ? `Measured on ${task.metric}` : null, task.check_on ? `checked ${task.check_on}` : null]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="mt-3 space-y-4 rounded-xl border border-[#ececec] bg-[#f6f7f7] p-4 text-sm text-[#4a5560]">
      <Detail label="Page">
        <a href={task.page} target="_blank" rel="noreferrer" className="break-all font-medium text-[#00857b] hover:underline">
          {task.page}
        </a>
      </Detail>
      {task.why ? <Detail label="Why this page">{task.why}</Detail> : null}
      {isGrowth ? <Parts task={task} clientId={clientId} onChange={onChange} /> : null}

      <div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
            {isGrowth ? "The parts, and what to do in each" : "Steps"}
          </span>
          {canEdit ? (
            <button
              type="button"
              onClick={() => (editing ? setEditing(false) : openEditor())}
              className="cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-3 py-1 text-xs font-semibold text-[#223540] hover:bg-[#eef8f7]"
            >
              {editing ? "Cancel editing" : "Edit steps & custom steps"}
            </button>
          ) : null}
        </div>

        <div className="mt-2">
          {editing ? (
            <div className="space-y-3 rounded-xl border border-[#ececec] bg-white p-3.5">
              {isGrowth ? (
                <>
                  {sections.map((sec, idx) => (
                    <div key={sec.uid} className="rounded-[10px] border border-[#f1f2f3] bg-[#f8f8f8] p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-bold text-[#0a0c0f]">
                            {idx + 1}. {sec.name}
                          </span>
                          {sec.custom ? <Pill t="ok">Custom</Pill> : null}
                        </div>
                        {sec.custom ? (
                          <button
                            type="button"
                            onClick={() => setSections((prev) => prev.filter((s) => s.uid !== sec.uid))}
                            className="cursor-pointer text-xs font-semibold text-[oklch(0.48_0.17_25)] hover:underline"
                          >
                            Remove custom step
                          </button>
                        ) : null}
                      </div>
                      <textarea
                        value={sec.stepsText}
                        onChange={(e) =>
                          setSections((prev) =>
                            prev.map((s) => (s.uid === sec.uid ? { ...s, stepsText: e.target.value } : s)),
                          )
                        }
                        rows={Math.min(8, Math.max(2, sec.stepsText.split("\n").length + 1))}
                        aria-label={`Steps for ${sec.name}`}
                        className="mt-2 w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-[13px] text-[#171a22] focus:border-[#00a99d] focus:outline-none"
                      />
                    </div>
                  ))}

                  <div className="rounded-[10px] border border-dashed border-[#d3d7d9] bg-white p-3">
                    <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                      Add custom step
                    </div>
                    <div className="mt-2 space-y-2">
                      <input
                        type="text"
                        value={newCustomName}
                        onChange={(e) => setNewCustomName(e.target.value)}
                        placeholder="Custom step title"
                        aria-label="Custom step title"
                        className="w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-1.5 text-[13px] text-[#171a22] placeholder:text-[#7a838c] focus:border-[#00a99d] focus:outline-none"
                      />
                      <textarea
                        value={newCustomBody}
                        onChange={(e) => setNewCustomBody(e.target.value)}
                        rows={2}
                        placeholder="Instructions (one per line, optional)"
                        aria-label="Custom step instructions"
                        className="w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-1.5 text-[13px] text-[#171a22] placeholder:text-[#7a838c] focus:border-[#00a99d] focus:outline-none"
                      />
                      <button
                        type="button"
                        disabled={!newCustomName.trim()}
                        onClick={addCustomSection}
                        className="cursor-pointer rounded-full border border-[#223540] bg-white px-3.5 py-1 text-xs font-semibold text-[#223540] hover:bg-[#eef8f7] disabled:opacity-45"
                      >
                        + Add to task
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="space-y-1.5">
                  <div className="text-xs text-[#7a838c]">One step per line — edit, reorder, or add custom steps below.</div>
                  <textarea
                    value={flatText}
                    onChange={(e) => setFlatText(e.target.value)}
                    rows={Math.min(12, Math.max(4, flatText.split("\n").length + 1))}
                    aria-label="Task steps"
                    className="w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-[13px] text-[#171a22] focus:border-[#00a99d] focus:outline-none"
                  />
                </div>
              )}

              {saveError ? (
                <p role="alert" className="text-xs text-red-800">
                  {saveError}
                </p>
              ) : null}

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={saving}
                  onClick={saveSteps}
                  className="cursor-pointer rounded-full bg-[#223540] px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save steps"}
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => setEditing(false)}
                  className="cursor-pointer rounded-full border border-[#e3e6e8] bg-white px-3.5 py-1.5 text-xs font-semibold text-[#4a5560]"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : task.steps.length > 0 ? (
            <Steps steps={task.steps} grouped={isGrowth} />
          ) : (
            <p className="text-xs text-[#7a838c]">No steps recorded yet.</p>
          )}
        </div>
      </div>

      {task.done_when ? <Detail label="Done when">{task.done_when}</Detail> : null}
      {measured || task.effort_min ? (
        <Detail label="Measured and sized">
          {[measured, task.effort_min ? `Estimated ${task.effort_min} minutes` : null].filter(Boolean).join(" · ")}
        </Detail>
      ) : null}
      {task.evidence.length > 0 ? (
        <Detail label="Evidence and limitations">
          <ul className="list-disc space-y-1 pl-5 text-[13px]">
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
            <a href={task.teamwork_task_url} target="_blank" rel="noreferrer" className="text-[#00857b] hover:underline">
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

function TaskRow({
  clientId,
  task,
  team,
  teamwork,
  rejectionReasons,
  onChange,
}: {
  clientId: string;
  task: EngineTask;
  team: { email: string; name: string | null }[];
  teamwork: TaskPlan["teamwork"];
  rejectionReasons: RejectionReason[];
  onChange: (task: EngineTask) => void;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [open, setOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);

  function run(task_: () => Promise<{ ok: true; value: EngineTask } | { ok: false; error: string }>) {
    setError(null);
    startTransition(async () => {
      const result = await task_();
      if (result.ok) {
        onChange(result.value);
        setRejectOpen(false);
      } else setError(result.error);
    });
  }

  return (
    <li className="py-3.5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 font-semibold text-[#0a0c0f]">
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              aria-label={`${open ? "Hide" : "Show"} the details of ${task.title}`}
              className="mr-0.5 inline-flex cursor-pointer align-middle text-[#4a5560] hover:text-[#0a0c0f]"
            >
              <ChevronRight size={16} aria-hidden className={`transition-transform ${open ? "rotate-90" : ""}`} />
            </button>
            <button type="button" onClick={() => setOpen((o) => !o)} className="cursor-pointer text-left hover:underline">
              {task.title}
            </button>
            {task.kind === "growth_action" ? (
              <Pill t="lime">growth action</Pill>
            ) : task.kind === "suggestion" ? (
              <Pill t="warn">confirmed by {task.confirmed_by.split("@")[0]}</Pill>
            ) : null}
          </div>
          <div className="mt-0.5 truncate pl-5 text-xs text-[#4a5560]" title={task.page}>
            “{task.search}” · {shortPage(task.page)}
          </div>
          {task.status === "shipped" && task.check_on ? (
            <div className="mt-0.5 pl-5 text-xs text-[#7a838c]">
              Shipped; its result shows on the monthly review from{" "}
              {new Date(`${task.check_on}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" })}.
            </div>
          ) : null}
        </div>
        <Pill t={STATUS_TONE[task.status] ?? "info"}>{task.status}</Pill>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-2 pl-5 text-xs">
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
            className="rounded-[10px] border border-[#e3e6e8] bg-white px-2.5 py-1 text-[#171a22]"
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
          className="rounded-[10px] border border-[#e3e6e8] bg-white px-2.5 py-1 text-[#171a22]"
        />

        {task.teamwork_task_url ? (
          <a href={task.teamwork_task_url} target="_blank" rel="noreferrer" className="font-semibold text-[#00857b] hover:underline">
            In Teamwork ↗
          </a>
        ) : teamwork.configured && teamwork.tasklist_id ? (
          <button
            type="button"
            disabled={pending}
            onClick={() => run(() => sendTaskAction(clientId, task.id))}
            className="cursor-pointer rounded-full bg-[#00a99d] px-3.5 py-1 font-semibold text-white hover:bg-[#008077] disabled:opacity-50"
          >
            {pending ? (
              <>
                <Spinner />
                Sending…
              </>
            ) : (
              "Send to Teamwork"
            )}
          </button>
        ) : (
          <span className="text-[#7a838c]">
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
          className="cursor-pointer font-semibold text-[#4a5560] hover:text-[#0a0c0f] hover:underline"
        >
          {copied ? "Copied ✓" : "Copy as text"}
        </button>

        {task.status !== "shipped" ? (
          <button
            type="button"
            disabled={pending}
            onClick={() => run(() => updateTaskAction(clientId, task.id, { status: "shipped" }))}
            className="cursor-pointer font-semibold text-[#2f5a00] hover:underline disabled:opacity-50"
          >
            Mark shipped
          </button>
        ) : null}

        <button
          type="button"
          disabled={pending}
          onClick={() => setRejectOpen((o) => !o)}
          className="cursor-pointer font-semibold text-[oklch(0.48_0.17_25)] hover:underline disabled:opacity-50"
        >
          {rejectOpen ? "Cancel" : "Drop / Reject"}
        </button>
      </div>

      {rejectOpen ? (
        <div className="mt-3 pl-5">
          <RejectForm
            reasons={rejectionReasons}
            busy={pending}
            allowDropWithoutReason
            onCancel={() => setRejectOpen(false)}
            onSubmit={(payload) =>
              run(() =>
                updateTaskAction(clientId, task.id, {
                  status: payload.status,
                  ...(payload.rejection_reason ? { rejection_reason: payload.rejection_reason } : {}),
                  ...(payload.rejection_note ? { rejection_note: payload.rejection_note } : {}),
                }),
              )
            }
          />
        </div>
      ) : null}

      {open ? <TaskDetails task={task} clientId={clientId} onChange={onChange} /> : null}
      {error ? (
        <p role="alert" className="mt-2 rounded-[10px] px-3 py-2 text-xs" style={toneStyle("miss")}>
          {error}
        </p>
      ) : null}
    </li>
  );
}

/** The month's work by the tool that does it: what is open, what is done, and what the page has been seen to show. */
function ByTool({ work }: { work: MonthWork }) {
  const { clientSlug } = useParams<{ clientSlug: string }>();
  const href = (t: WorkTool, i: WorkTool["items"][number]) =>
    t.path && t.param
      ? `/${clientSlug}${t.path}?${t.param}=${encodeURIComponent(t.param === "term" ? i.search : i.page)}${i.kind ? `&kind=${i.kind}` : ""}&from=plan`
      : null;
  return (
    <div className="mt-5 border-t border-[#ececec] pt-4">
      <h3 className="font-[var(--font-heading)] text-sm font-bold text-[#0a0c0f]">This month&apos;s work, by tool</h3>
      <p className="mt-1 text-xs text-[#4a5560]">
        {work.done} of {work.parts} parts done{work.seen_live ? `, ${work.seen_live} seen live on the page` : ""}. See them measured in{" "}
        <Link href={`/${clientSlug}/annotations`} className="font-semibold text-[#00857b] hover:underline">
          Annotations
        </Link>
        .
      </p>
      <ul className="mt-2 divide-y divide-[#f1f2f3] text-sm">
        {work.by_tool.map((t) => (
          <li key={t.tool} className="py-2">
            <details>
              <summary className="flex cursor-pointer flex-wrap items-baseline justify-between gap-2">
                <span className="font-semibold text-[#0a0c0f]">{t.label}</span>
                <span className="text-xs tabular-nums text-[#7a838c]">
                  {t.open} open · {t.done} done{t.seen_live ? ` · ${t.seen_live} seen live` : ""}
                </span>
              </summary>
              <ul className="mt-2 space-y-1 pl-3 text-xs">
                {t.items.map((i) => {
                  const to = href(t, i);
                  return (
                    <li key={`${i.task_id}-${i.part}`} className="flex flex-wrap items-center justify-between gap-2">
                      <span className={i.done ? "text-[#7a838c] line-through" : "text-[#171a22]"}>
                        {i.name} <span className="text-[#7a838c]">· {shortPage(i.page)}</span>
                        {i.seen_live ? <span className="ml-1 font-semibold text-[#00665f]">✓ seen live</span> : null}
                      </span>
                      {!i.done && to ? (
                        <Link href={to} className="font-semibold text-[#00857b] hover:underline">
                          Open
                        </Link>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function EnginePlan({
  clientId,
  month,
  tasks,
  allowance,
  teamwork,
  work: firstWork,
  team,
  onTaskChange,
  rejectionReasons = REJECTION_REASONS,
  styleNotes,
}: {
  clientId: string;
  month: string;
  tasks: EngineTask[];
  allowance: Allowance;
  teamwork: TaskPlan["teamwork"];
  work: MonthWork | null;
  team: { email: string; name: string | null }[];
  onTaskChange: (task: EngineTask) => void;
  rejectionReasons?: RejectionReason[];
  styleNotes?: string | null;
}) {
  const { clientSlug } = useParams<{ clientSlug: string }>();
  const live = tasks.filter((t) => t.status !== "dropped" && t.status !== "rejected");
  const inactive = tasks.filter((t) => t.status === "rejected" || t.status === "dropped");
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);

  // The counts come from the server, so they are asked for again when a task changes (a part marked done, a subtask ticked, a page seen live).
  const [work, setWork] = useState<MonthWork | null>(firstWork);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    workAction(clientId, month).then((w) => w && setWork(w));
  }, [tasks, clientId, month]);
  const pct = allowance.monthly ? Math.min(100, (allowance.used / allowance.monthly) * 100) : 0;

  async function restoreTask(task: EngineTask) {
    setRestoringId(task.id);
    setRestoreError(null);
    const r = await updateTaskAction(clientId, task.id, { status: "confirmed" });
    setRestoringId(null);
    if (r.ok) onTaskChange(r.value);
    else setRestoreError(r.error);
  }

  return (
    <div className="mb-6 rounded-xl border border-[#ececec] bg-white p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">Monthly plan</span>
          <h2 className="font-[var(--font-heading)] text-lg font-bold text-[#0a0c0f]">Plan for {monthLabel(month)}</h2>
        </div>
        {allowance.monthly != null ? (
          <span
            className={`text-sm tabular-nums ${
              allowance.over ? "font-semibold text-amber-800" : "text-[#4a5560]"
            }`}
          >
            {allowance.used} of {allowance.monthly} growth actions
            {allowance.over ? ": over the plan" : ""}
          </span>
        ) : (
          <span className="text-sm text-[#4a5560]">{allowance.used} confirmed</span>
        )}
      </div>

      {allowance.monthly != null ? (
        <div className="mt-2 h-1.5 rounded-full bg-[#eef0f1]">
          <div
            className={`h-1.5 rounded-full ${allowance.over ? "bg-amber-500" : "bg-[#00a99d]"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      ) : null}

      {clientSlug ? (
        <div className="mt-3">
          <StyleNotesBanner styleNotes={styleNotes} clientSlug={clientSlug} compact />
        </div>
      ) : null}

      {live.length === 0 ? (
        <p className="mt-3 text-sm text-[#4a5560]">
          Nothing confirmed yet. Diagnose a page above and confirm what you want done: it becomes a task here, and from here it goes to Teamwork.
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-[#f1f2f3] text-sm">
          {live.map((t) => (
            <TaskRow
              key={t.id}
              clientId={clientId}
              task={t}
              team={team}
              teamwork={teamwork}
              rejectionReasons={rejectionReasons}
              onChange={onTaskChange}
            />
          ))}
        </ul>
      )}

      {inactive.length > 0 ? (
        <div className="mt-5 border-t border-[#ececec] pt-4">
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
            Rejected &amp; dropped ({inactive.length})
          </div>
          {restoreError ? (
            <p role="alert" className="mt-2 text-xs text-red-800">
              {restoreError}
            </p>
          ) : null}
          <ul className="mt-2 space-y-2 text-xs">
            {inactive.map((t) => {
              const reasonLabel =
                t.rejection_reason_label ??
                rejectionReasons.find((r) => r.key === t.rejection_reason)?.label ??
                t.rejection_reason;
              return (
                <li
                  key={t.id}
                  className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-[#ececec] bg-[#f8f8f8] px-3.5 py-2.5"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Pill t={t.status === "rejected" ? "miss" : "warn"}>{t.status}</Pill>
                      {reasonLabel ? <Pill t="info">{reasonLabel}</Pill> : null}
                      <span className="font-semibold text-[#0a0c0f]">{t.title}</span>
                    </div>
                    <div className="mt-1 text-[#4a5560]">
                      “{t.search}” · {shortPage(t.page)}
                      {t.rejected_at ? ` · ${formatDay(t.rejected_at, true)}` : ""}
                      {t.rejected_by ? ` by ${t.rejected_by.split("@")[0]}` : ""}
                    </div>
                    {t.rejection_note ? <p className="mt-1 text-[#171a22]">{t.rejection_note}</p> : null}
                  </div>
                  <button
                    type="button"
                    disabled={restoringId === t.id}
                    onClick={() => restoreTask(t)}
                    className="cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-3 py-1 text-xs font-semibold text-[#223540] hover:bg-[#eef8f7] disabled:opacity-50"
                  >
                    {restoringId === t.id ? "Restoring…" : "Restore"}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {work && work.parts > 0 ? <ByTool work={work} /> : null}
    </div>
  );
}
