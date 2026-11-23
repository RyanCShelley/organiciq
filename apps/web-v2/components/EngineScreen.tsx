"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import {
  confirmTaskAction,
  diagnoseAction,
  diagnosePagesAction,
  rejectTaskAction,
} from "@/app/(app)/[clientSlug]/engine/actions";
import { saveFocusAction } from "@/app/(app)/[clientSlug]/focus/actions";
import { EnginePlan } from "@/components/EnginePlan";
import { EngineWorkbench } from "@/components/EngineWorkbench";
import { GrowthActionPlanner } from "@/components/GrowthActionPlanner";
import { ChecklistPanel } from "@/components/diagnose/ChecklistPanel";
import { ContextHeader } from "@/components/diagnose/ContextHeader";
import { PageHistoryPanel } from "@/components/diagnose/PageHistoryPanel";
import { StyleNotesBanner } from "@/components/diagnose/StyleNotesBanner";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import {
  REJECTION_REASONS,
  type Allowance,
  type Candidate,
  type Diagnosis,
  type EngineKind,
  type EngineOverview,
  type EngineTask,
  type LeadsCandidates,
  type RejectionReason,
  type TaskDraft,
  type TaskPlan,
  type TrafficCandidates,
  type VisibilityCandidates,
} from "@/lib/engine";
import { FOCUSES, monthLabel, type ClientFocus } from "@/lib/focus";

const num = (n: number | null | undefined, digits = 0) =>
  n == null ? "–" : n.toLocaleString(undefined, { maximumFractionDigits: digits });

function shortPage(url: string): string {
  return url.replace(/^https?:\/\/[^/]+/, "") || "/";
}

function ConfirmButton({
  clientId,
  month,
  draft,
  existing,
  onConfirmed,
}: {
  clientId: string;
  month: string;
  draft: TaskDraft;
  existing: EngineTask | undefined;
  onConfirmed: (task: EngineTask) => void;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  if (existing) {
    return (
      <span className="rounded-full bg-[#e6f7f5] px-3 py-1 text-xs font-semibold text-[#00665f]">
        ✓ In the plan ({existing.status})
      </span>
    );
  }
  return (
    <span className="inline-flex flex-col items-end gap-1">
      <button
        type="button"
        disabled={pending}
        onClick={() =>
          startTransition(async () => {
            setError(null);
            const result = await confirmTaskAction(clientId, month, draft);
            if (result.ok) onConfirmed(result.value);
            else setError(result.error);
          })
        }
        className="cursor-pointer rounded-full bg-[#223540] px-3.5 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-[#00a99d] disabled:opacity-50"
      >
        {pending ? (
          <>
            <Spinner />
            Adding…
          </>
        ) : draft.kind === "suggestion" ? (
          "Confirm as a task"
        ) : (
          "Add to the plan"
        )}
      </button>
      {error ? <span className="max-w-[16rem] text-right text-xs text-[oklch(0.48_0.17_25)]">{error}</span> : null}
    </span>
  );
}

function DirectRejectButton({
  clientId,
  month,
  kind,
  ruleId,
  search,
  page,
  title,
  why,
  steps,
  reasons,
  onRejected,
}: {
  clientId: string;
  month: string;
  kind: "prescription" | "suggestion";
  ruleId: string;
  search: string;
  page: string;
  title: string;
  why: string;
  steps: string[];
  reasons: RejectionReason[];
  onRejected: (task: EngineTask) => void;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState(reasons[0]?.key ?? "wrong_intent");
  const [note, setNote] = useState("");
  const [doneLabel, setDoneLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  if (doneLabel) {
    return (
      <span className="rounded-full bg-[oklch(0.965_0.025_25)] px-2.5 py-1 text-[11px] font-semibold text-[oklch(0.48_0.17_25)]">
        Rejected · {doneLabel}
      </span>
    );
  }

  return (
    <div className="inline-flex flex-col items-end gap-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="cursor-pointer rounded-full border border-[oklch(0.88_0.06_25)] bg-white px-3 py-1 text-xs font-semibold text-[oklch(0.48_0.17_25)] hover:bg-[oklch(0.965_0.025_25)]"
      >
        {open ? "Cancel reject" : "Reject"}
      </button>
      {open ? (
        <div className="mt-1 w-72 rounded-xl border border-[oklch(0.88_0.06_25)] bg-white p-3 text-left text-xs">
          <label className="block font-semibold text-[#171a22]">
            Reason
            <select
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="mt-1 w-full rounded-[10px] border border-[#e3e6e8] bg-white px-2.5 py-1.5 text-xs font-normal text-[#171a22]"
            >
              {reasons.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional note…"
            className="mt-2 w-full rounded-[10px] border border-[#e3e6e8] bg-white px-2.5 py-1.5 text-xs text-[#171a22] placeholder:text-[#7a838c]"
          />
          {error ? <p className="mt-1 text-[oklch(0.48_0.17_25)]">{error}</p> : null}
          <button
            type="button"
            disabled={pending}
            onClick={() =>
              start(async () => {
                setError(null);
                const r = await rejectTaskAction(clientId, {
                  month,
                  kind,
                  rule_id: ruleId,
                  search,
                  page,
                  title,
                  why,
                  steps,
                  rejection_reason: reason,
                  rejection_note: note.trim() || undefined,
                });
                if (r.ok) {
                  onRejected(r.value);
                  setDoneLabel(r.value.rejection_reason_label ?? reason);
                  setOpen(false);
                } else {
                  setError(r.error);
                }
              })
            }
            className="mt-2 cursor-pointer rounded-full bg-[oklch(0.48_0.17_25)] px-3 py-1 text-xs font-semibold text-white disabled:opacity-50"
          >
            {pending ? "Saving…" : "Confirm rejection"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function suggestionBadge(id: string): { label: string; cls: string } | null {
  if (id === "MC-1") return { label: "MC-1 · Meta & CTR", cls: "bg-[#e6f7f5] text-[#00665f]" };
  if (id === "FQ-1") return { label: "FQ-1 · FAQ page link", cls: "bg-[#e6f7f5] text-[#00665f]" };
  if (id === "S-2") return { label: "S-2 · FAQ & PAA", cls: "bg-[#e9fedc] text-[#2f5a00]" };
  return null;
}

export function EngineScreen({
  client,
  workMonth,
  focus,
  buckets,
  bucketId,
  kind,
  data,
  traffic,
  leads,
  overview,
  plan,
  team,
  error,
  rejectionReasons,
  initialTerm,
}: {
  client: Client;
  workMonth: string;
  focus: ClientFocus | null;
  buckets: { id: string; name: string }[];
  bucketId: string | null;
  kind: EngineKind | null;
  data: VisibilityCandidates | null;
  traffic: TrafficCandidates | null;
  leads: LeadsCandidates | null;
  overview: EngineOverview;
  plan: TaskPlan;
  team: { email: string; name: string | null }[];
  error: string | null;
  rejectionReasons?: RejectionReason[];
  initialTerm?: string | null;
}) {
  const router = useRouter();
  const [switching, startSwitch] = useTransition();
  const [switchError, setSwitchError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<EngineTask[]>(plan.tasks);
  const [picked, setPicked] = useState<string[]>([]);
  // After a diagnosis the candidate list folds away so the diagnosis is the first thing on the screen.
  const [collapsed, setCollapsed] = useState(false);
  const [diagnoses, setDiagnoses] = useState<Diagnosis[] | null>(null);
  const [diagnoseError, setDiagnoseError] = useState<string | null>(null);
  const [diagnosing, startDiagnose] = useTransition();
  const advice = overview.advice;
  const reasons = rejectionReasons && rejectionReasons.length > 0 ? rejectionReasons : REJECTION_REASONS;

  const norm = (text: string) => text.toLowerCase().split(/\s+/).filter(Boolean).join(" ");
  const live = tasks.filter((t) => t.status !== "dropped" && t.status !== "rejected");
  const allowance: Allowance = {
    monthly: plan.allowance.monthly,
    used: new Set(live.map((t) => t.page)).size,
    over: plan.allowance.monthly != null && new Set(live.map((t) => t.page)).size > plan.allowance.monthly,
  };

  function upsertTask(task: EngineTask) {
    setTasks((current) =>
      current.some((t) => t.id === task.id) ? current.map((t) => (t.id === task.id ? task : t)) : [...current, task],
    );
  }

  function existingFor(ruleId: string, search: string, page: string): EngineTask | undefined {
    return live.find((t) => t.rule_id === ruleId && t.search === norm(search) && t.page === page);
  }

  function diagnosePages(pages: string[]) {
    if (!pages.length || (kind !== "traffic" && kind !== "leads")) return;
    setDiagnoseError(null);
    startDiagnose(async () => {
      const result = await diagnosePagesAction(client.id, kind, pages);
      if (result.ok) {
        setDiagnoses(result.results);
        setCollapsed(true);
      } else setDiagnoseError(result.error);
    });
  }

  /** Drop this diagnosis and untick it. With none left, bring the candidate list back to pick another. */
  function removeDiagnosis(d: Diagnosis) {
    const key = `${d.search}|${d.page}`;
    setPicked((current) => current.filter((k) => k !== key));
    const rest = (diagnoses ?? []).filter((x) => `${x.search}|${x.page}` !== key);
    if (rest.length === 0) {
      setDiagnoses(null);
      setCollapsed(false);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else setDiagnoses(rest);
  }

  function scopeTo(bucketKey: string) {
    router.push(`/${client.slug}/engine?bucket=${bucketKey}${kind && kind !== focus?.focus ? `&show=${kind}` : ""}`);
  }

  function diagnose() {
    if (!data) return;
    setDiagnoseError(null);
    const selections = picked
      .map((key) => data.candidates.find((c) => `${c.search}|${c.page}` === key))
      .filter((c): c is Candidate => Boolean(c))
      .map((c) => ({ search: c.search, page: c.page }));
    startDiagnose(async () => {
      const result = await diagnoseAction(client.id, selections, kind);
      if (result.ok) {
        setDiagnoses(result.results);
        setCollapsed(true);
      } else setDiagnoseError(result.error);
    });
  }
  const buckets_ = overview.buckets;

  function switchTo(targetBucketId: string) {
    setSwitchError(null);
    startSwitch(async () => {
      const result = await saveFocusAction(client.id, client.slug, workMonth, "visibility", targetBucketId);
      if (result.ok) router.push(`/${client.slug}/engine`);
      else setSwitchError(result.error);
    });
  }
  const focusLabel = FOCUSES.find((f) => f.value === focus?.focus)?.label;

  // Keep lint/unused-var clean while retaining diagnose handler for plain visibility diagnosis if invoked
  void diagnose;

  return (
    <section className={kind !== null ? "max-w-[90rem]" : "max-w-6xl"}>
      {kind !== null ? (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex flex-wrap items-center gap-3 text-[#4a5560]">
            <h1 className="font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">Decision engine</h1>
            <span className="h-4 w-px bg-[#e3e6e8]" />
            <span>
              <strong className="text-[#0a0c0f]">{monthLabel(workMonth)} focus:</strong>{" "}
              {focus ? (
                <>
                  {focusLabel}
                  {focus.bucket_name ? ` · ${focus.bucket_name}` : ""}
                </>
              ) : (
                "not set"
              )}
            </span>
            <Link href={`/${client.slug}/review`} className="font-semibold text-[#00857b] hover:underline">
              {focus ? "Change" : "Choose it"} →
            </Link>
          </div>
          <div className="flex rounded-full bg-[#f1f3f4] p-[3px]" role="tablist" aria-label="Focus">
            {FOCUSES.map((f) => (
              <Link
                key={f.value}
                role="tab"
                aria-selected={kind === f.value}
                href={`/${client.slug}/engine?show=${f.value}${bucketId ? `&bucket=${bucketId}` : ""}`}
                className="rounded-full px-3 py-1 font-semibold"
                style={kind === f.value ? { background: "#223540", color: "#fff" } : undefined}
              >
                {f.label}
              </Link>
            ))}
          </div>
        </div>
      ) : null}

      <header className={kind !== null ? "hidden" : "mb-5"}>
        <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">{client.client_name}</div>
        <h1 className="mt-0.5 font-[var(--font-heading)] text-2xl font-bold text-[#0a0c0f]">Decision engine</h1>
      </header>

      <div
        className={`mb-5 flex-wrap items-center justify-between gap-3 rounded-xl border border-[#ececec] bg-white px-4 py-3.5 text-sm ${
          kind !== null ? "hidden" : "flex"
        }`}
      >
        {focus ? (
          <span className="text-[#171a22]">
            Focus for <strong>{monthLabel(workMonth)}</strong>: <strong>{focusLabel}</strong>
            {focus.bucket_name ? <> · {focus.bucket_name}</> : " · no bucket chosen"}
          </span>
        ) : (
          <span className="text-[#4a5560]">
            No focus is set for <strong>{monthLabel(workMonth)}</strong>.
          </span>
        )}
        <a href="#plan" className="text-[#4a5560] hover:text-[#0a0c0f] hover:underline">
          {monthLabel(workMonth)} plan: <strong>{allowance.used}{allowance.monthly != null ? ` of ${allowance.monthly}` : ""}</strong> growth actions ↓
        </a>
        <Link href={`/${client.slug}/review`} className="font-semibold text-[#00857b] hover:underline">
          {focus ? "Change on the monthly review →" : "Choose it on the monthly review →"}
        </Link>
      </div>

      <div
        className={`mb-5 flex-wrap items-center gap-2 text-xs ${kind !== null ? "hidden" : "flex"}`}
        role="tablist"
        aria-label="Focus"
      >
        {FOCUSES.map((f) => {
          const on = kind === f.value;
          return (
            <Link
              key={f.value}
              role="tab"
              aria-selected={on}
              href={`/${client.slug}/engine?show=${f.value}${bucketId ? `&bucket=${bucketId}` : ""}`}
              className={`rounded-full border px-4 py-1.5 font-semibold transition-colors ${
                on
                  ? "border-[#223540] bg-[#223540] text-white"
                  : "border-[#e3e6e8] bg-white text-[#4a5560] hover:border-[#00a99d] hover:text-[#0a0c0f]"
              }`}
            >
              {f.label}
              {focus?.focus === f.value ? (
                <span className={`ml-2 text-[11px] ${on ? "text-white/80" : "text-[#00857b]"}`}>this month&apos;s focus</span>
              ) : null}
            </Link>
          );
        })}
      </div>

      {kind === "visibility" && advice.level !== "ok" && advice.headline ? (
        <div
          className={`mb-6 rounded-xl border p-5 text-sm ${
            advice.level === "thin_data"
              ? "border-[oklch(0.88_0.06_25)] bg-[oklch(0.965_0.025_25)] text-[oklch(0.48_0.17_25)]"
              : "border-[oklch(0.88_0.08_85)] bg-[oklch(0.97_0.045_85)] text-[oklch(0.42_0.1_65)]"
          }`}
        >
          <h2 className="font-[var(--font-heading)] font-bold">{advice.headline}</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {advice.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          {advice.suggestions.length > 0 ? (
            <div className="mt-3 space-y-2">
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] opacity-75">What you could do</div>
              {advice.suggestions.map((s) => (
                <div key={s.text} className="flex flex-wrap items-center justify-between gap-3">
                  <span>{s.text}</span>
                  {s.kind === "bucket" && s.bucket_id ? (
                    <button
                      type="button"
                      disabled={switching}
                      onClick={() => switchTo(s.bucket_id as string)}
                      className="cursor-pointer rounded-full bg-[#223540] px-3.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      Switch the focus to {s.name}
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          {switchError ? (
            <p role="alert" className="mt-3 text-[oklch(0.48_0.17_25)]">
              {switchError}
            </p>
          ) : null}
        </div>
      ) : null}

      {!kind ? (
        <div className="rounded-xl border border-dashed border-[#d3d7d9] bg-white p-6 text-sm text-[#4a5560]">
          No focus is set for this month. Choose one on the monthly review, or open any tab above to look at its candidates.
        </div>
      ) : null}

      {kind === "visibility" && buckets_.length > 0 ? (
        <details className="mb-3 rounded-xl border border-[#ececec] bg-white px-4 py-2 text-sm">
          <summary className="cursor-pointer text-xs font-semibold text-[#4a5560]">What each bucket has to move</summary>
          <p className="mt-1 text-sm text-[#4a5560]">
            Searches where a page already ranks 2 to 20. A bucket with nothing here needs pages built for its terms before there is anything to move.
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="text-[11px] uppercase tracking-wide text-[#7a838c]">
                <tr>
                  <th className="py-1 pr-3 font-medium">Bucket</th>
                  <th className="px-3 py-1 text-right font-medium">Searches in reach</th>
                  <th className="px-3 py-1 text-right font-medium">Strong</th>
                  <th className="px-3 py-1 text-right font-medium">Extra clicks (top 20)</th>
                  <th className="py-1 pl-3 text-right font-medium">Terms with no impressions</th>
                </tr>
              </thead>
              <tbody>
                {buckets_.map((b) => (
                  <tr
                    key={b.id}
                    onClick={() => router.push(`/${client.slug}/engine?bucket=${b.id}${focus ? "" : "&show=visibility"}`)}
                    className={`cursor-pointer border-t border-[#f1f2f3] hover:bg-[#f8f8f8] ${
                      b.id === bucketId ? "bg-[#eef8f7] font-semibold" : ""
                    }`}
                  >
                    <td className="py-2 pr-3">
                      {b.name}
                      {focus?.bucket_id === b.id ? (
                        <span className="ml-2 rounded-full bg-[#e6f7f5] px-2 py-0.5 text-[10px] font-semibold text-[#00665f]">
                          focus
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{b.found.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{b.strong}</td>
                    <td className="px-3 py-2 text-right tabular-nums">+{num(b.expected_extra_clicks, 1)}</td>
                    <td className="py-2 pl-3 text-right tabular-nums">
                      {b.unranked_terms} of {b.terms}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}

      {error ? (
        <p
          role="alert"
          className="mb-4 rounded-xl border border-[oklch(0.88_0.06_25)] bg-[oklch(0.965_0.025_25)] p-4 text-sm text-[oklch(0.48_0.17_25)]"
        >
          {error}
        </p>
      ) : null}

      {diagnoseError ? (
        <p
          role="alert"
          className="mb-4 rounded-xl border border-[oklch(0.88_0.06_25)] bg-[oklch(0.965_0.025_25)] p-4 text-sm text-[oklch(0.48_0.17_25)]"
        >
          {diagnoseError}
        </p>
      ) : null}

      {(kind === "visibility" && data) || (kind === "traffic" && traffic) || (kind === "leads" && leads) ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label>
              <span className="font-semibold text-[#171a22]">Scope</span>
              <select
                value={bucketId ?? "site"}
                onChange={(e) => scopeTo(e.target.value)}
                className="ml-2 rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-1.5 text-sm text-[#171a22]"
              >
                <option value="site">Whole site</option>
                {buckets.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </label>
            {kind === "visibility" && data ? (
              <span className="text-xs text-[#4a5560]">
                Searches where a page ranks 2 to 20, read over {data.window.from} to {data.window.to}. {data.counts.strong} strong ·{" "}
                {data.counts.possible.toLocaleString()} possible · top {data.counts.listed} listed.
              </span>
            ) : kind === "traffic" && traffic ? (
              <span className="text-xs text-[#4a5560]">
                Organic sessions that fell against the site&apos;s own trend ({traffic.windows.three_months[0]} to {traffic.windows.three_months[1]}).{" "}
                {traffic.counts.strong} strong · {traffic.counts.possible} possible · {traffic.dropped_pages.length} listed.
              </span>
            ) : kind === "leads" && leads ? (
              <span className="text-xs text-[#4a5560]">
                Pages lagging on {leads.noun.plural} ({leads.window.from} to {leads.window.to}).{" "}
                {leads.counts.strong} strong · {leads.counts.possible} possible · {leads.candidates.length} listed.
              </span>
            ) : null}
          </div>

          {kind === "leads" && leads?.needs === "conversions" ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[oklch(0.88_0.08_85)] bg-[oklch(0.97_0.045_85)] px-4 py-3 text-sm text-[oklch(0.42_0.1_65)]">
              <span>No conversion events are chosen yet for this client, so lead rates cannot be compared.</span>
              <Link href={`/${client.slug}/settings/conversions`} className="font-semibold underline">
                Choose conversion events →
              </Link>
            </div>
          ) : null}

          <EngineWorkbench
            clientId={client.id}
            clientSlug={client.slug}
            month={workMonth}
            monthName={monthLabel(workMonth).split(" ")[0]}
            data={data}
            traffic={traffic}
            leads={leads}
            tasks={tasks}
            allowance={allowance}
            teamworkReady={plan.teamwork.configured && Boolean(plan.teamwork.tasklist_id)}
            onTaskChange={upsertTask}
            focus={kind}
            rejectionReasons={reasons}
            styleNotes={client.style_notes ?? null}
            initialTerm={initialTerm}
          />
          {kind === "visibility" && data && (data.unranked.length > 0 || data.notes.length > 0) ? (
            <details className="rounded-xl border border-[#ececec] bg-white p-4 text-sm">
              <summary className="cursor-pointer font-semibold text-[#0a0c0f]">
                About this list
                {data.unranked.length > 0 ? ` · ${data.unranked.length} watchlist terms with no Google impressions` : ""}
              </summary>
              {data.unranked.length > 0 ? (
                <ul className="mt-3 divide-y divide-[#f1f2f3]">
                  {data.unranked.map((u) => (
                    <li key={u.keyword} className="flex items-center justify-between gap-4 py-2">
                      <span className="font-medium text-[#0a0c0f]">{u.keyword}</span>
                      <span className="text-[#4a5560]">{num(u.volume)} searches a month</span>
                      <span className="rounded-full bg-[#f1f3f4] px-2.5 py-0.5 text-xs font-semibold text-[#4a5560]">
                        {u.strength}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
              <ul className="mt-3 space-y-1 text-xs text-[#7a838c]">
                {data.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      ) : null}

      {diagnoses ? (
        <div className="mt-6 space-y-4">
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
            Page diagnosis ({diagnoses.length})
          </div>

          {diagnoses.map((d) => {
            const activeDiagFocus = d.focus ?? kind ?? "visibility";
            return (
              <div
                key={`${d.search}|${d.page}`}
                className="space-y-4 rounded-xl border border-[#ececec] bg-white p-5"
              >
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#ececec] pb-4">
                  <div className="min-w-0">
                    <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                      Diagnosed page · {activeDiagFocus}
                    </div>
                    <h3 className="mt-0.5 font-[var(--font-heading)] text-[20px] font-bold text-[#0a0c0f]">
                      {d.search.startsWith("(") ? shortPage(d.page) : d.search}
                    </h3>
                    <p className="mt-0.5 text-xs text-[#4a5560]">
                      {d.search.startsWith("(") ? d.page.replace(/^https?:\/\//, "") : shortPage(d.page)}
                      {d.position != null
                        ? ` · position ${d.position} · ${num(d.impressions)} impressions · ${num(d.clicks)} clicks`
                        : ""}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeDiagnosis(d)}
                    className="shrink-0 cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-3.5 py-1.5 text-xs font-semibold text-[#223540] transition-colors hover:border-[oklch(0.88_0.06_25)] hover:bg-[oklch(0.965_0.025_25)] hover:text-[oklch(0.48_0.17_25)]"
                  >
                    Remove and choose a different one
                  </button>
                </div>

                {!d.read.ok ? (
                  <p
                    role="alert"
                    className="rounded-xl border border-[oklch(0.88_0.06_25)] bg-[oklch(0.965_0.025_25)] p-3.5 text-sm text-[oklch(0.48_0.17_25)]"
                  >
                    Could not read this page: {d.read.error}
                  </p>
                ) : (
                  <>
                    <ContextHeader
                      intent={d.context?.intent}
                      pageType={d.context?.page_type}
                      fit={d.context?.fit}
                      template={d.context?.template}
                      focus={activeDiagFocus}
                      focusOrderReason={d.focus_order_reason}
                    />

                    <StyleNotesBanner styleNotes={d.context?.style_notes} />

                    {d.read.source === "crawl" ? (
                      <p className="rounded-[10px] border border-[oklch(0.88_0.08_85)] bg-[oklch(0.97_0.045_85)] px-3.5 py-2.5 text-xs text-[oklch(0.42_0.1_65)]">
                        <span className="font-semibold">Read from the site crawl, not the live page.</span> {d.read.source_note}.
                      </p>
                    ) : null}

                    {d.observations.filter((o) => o.level === "problem" || Boolean(d.read.blocked)).length > 0 ? (
                      <ul className="space-y-1.5 rounded-[10px] border border-[#ececec] bg-[#f8f8f8] px-3.5 py-3 text-sm">
                        {d.observations
                          .filter((o) => o.level === "problem" || Boolean(d.read.blocked))
                          .map((o) => (
                            <li
                              key={o.text}
                              className={
                                o.level === "problem"
                                  ? "text-[oklch(0.48_0.17_25)]"
                                  : o.level === "ok"
                                    ? "text-[#00857b]"
                                    : "text-[#4a5560]"
                              }
                            >
                              {o.level === "problem" ? "⚠ " : o.level === "ok" ? "✓ " : "• "}
                              {o.text}
                              {o.how ? (
                                <details className="ml-5 mt-0.5 text-xs text-[#4a5560]">
                                  <summary className="cursor-pointer font-semibold">How we know</summary>
                                  <p className="mt-1">{o.how}</p>
                                </details>
                              ) : null}
                            </li>
                          ))}
                      </ul>
                    ) : null}

                    {d.read.received && d.read.blocked ? (
                      <details className="rounded-[10px] border border-[#ececec] bg-[#f8f8f8] p-3 text-xs text-[#4a5560]" open>
                        <summary className="cursor-pointer font-semibold text-[#0a0c0f]">What we received</summary>
                        <dl className="mt-1 grid grid-cols-[7rem_1fr] gap-x-2 gap-y-0.5">
                          <dt>Asked for</dt>
                          <dd className="break-all">{d.read.received.requested_url ?? d.read.received.final_url}</dd>
                          <dt>Answer</dt>
                          <dd>
                            HTTP {d.read.received.status}, {d.read.received.bytes.toLocaleString()} bytes
                          </dd>
                          <dt>Asked as</dt>
                          <dd>{d.read.received.user_agent ?? "unknown"}</dd>
                          {Object.entries(d.read.received.headers).map(([k, v]) => (
                            <span key={k} className="contents">
                              <dt>{k}</dt>
                              <dd className="break-all">{v}</dd>
                            </span>
                          ))}
                          <dt>Started with</dt>
                          <dd className="break-all font-mono">{d.read.received.body_starts || "(nothing)"}</dd>
                        </dl>
                      </details>
                    ) : null}

                    {d.prescriptions.length > 0 || d.suggestions.length > 0 ? (
                      <div className="space-y-3 rounded-xl border border-[#ececec] bg-white p-4">
                        <div>
                          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                            Direct page findings · focus-ordered
                          </div>
                          {d.focus_order_reason ? (
                            <p className="mt-0.5 text-xs text-[#4a5560]">{d.focus_order_reason}</p>
                          ) : null}
                        </div>

                        <ul className="space-y-2.5">
                          {d.prescriptions.map((p) => {
                            const draft: TaskDraft = {
                              kind: "prescription",
                              rule_id: p.action_id,
                              search: d.search,
                              page: d.page,
                              title: p.title,
                              why: p.why,
                              steps: p.steps,
                              done_when: p.done_when,
                              metric: p.metric,
                              effort_min: p.effort_min,
                              evidence: p.evidence,
                            };
                            const existing = existingFor(p.action_id, d.search, d.page);
                            return (
                              <li key={p.action_id} className="rounded-[10px] border border-[#ececec] bg-[#f8f8f8] p-3.5 text-sm">
                                <div className="flex flex-wrap items-start justify-between gap-2">
                                  <div className="min-w-0 flex-1">
                                    <div className="flex flex-wrap items-center gap-1.5">
                                      <span className="rounded-full bg-[#e6f7f5] px-2.5 py-0.5 text-[10px] font-semibold text-[#00665f]">
                                        Rule {p.action_id}
                                      </span>
                                      <span className="rounded-full bg-[#f1f3f4] px-2 py-0.5 text-[10px] font-semibold text-[#4a5560]">
                                        ~{p.effort_min} min
                                      </span>
                                    </div>
                                    <h4 className="mt-1 font-[var(--font-heading)] text-sm font-bold text-[#0a0c0f]">
                                      {p.title}
                                    </h4>
                                  </div>
                                  <div className="flex flex-wrap items-center gap-2">
                                    <ConfirmButton
                                      clientId={client.id}
                                      month={workMonth}
                                      draft={draft}
                                      existing={existing}
                                      onConfirmed={upsertTask}
                                    />
                                    {!existing ? (
                                      <DirectRejectButton
                                        clientId={client.id}
                                        month={workMonth}
                                        kind="prescription"
                                        ruleId={p.action_id}
                                        search={d.search}
                                        page={d.page}
                                        title={p.title}
                                        why={p.why}
                                        steps={p.steps}
                                        reasons={reasons}
                                        onRejected={upsertTask}
                                      />
                                    ) : null}
                                  </div>
                                </div>
                                <p className="mt-1 text-[13px] text-[#4a5560]">{p.why}</p>
                                {p.steps.length > 0 ? (
                                  <div className="mt-2.5 space-y-1.5">
                                    {p.steps.map((step, idx) => (
                                      <div key={idx} className="flex items-start gap-2.5 text-[13px] text-[#171a22]">
                                        <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-[#223540] text-[11px] font-bold text-white">
                                          {idx + 1}
                                        </span>
                                        <span>{step}</span>
                                      </div>
                                    ))}
                                  </div>
                                ) : null}
                              </li>
                            );
                          })}

                          {d.suggestions.map((s) => {
                            const badge = suggestionBadge(s.id);
                            const draft: TaskDraft = {
                              kind: "suggestion",
                              rule_id: s.id,
                              search: d.search,
                              page: d.page,
                              title: s.id === "MC-1" ? "Rewrite the meta for clicks" : s.title,
                              why: s.why,
                              steps: s.steps,
                              done_when: null,
                              metric: null,
                              effort_min: null,
                              evidence: s.evidence,
                            };
                            const existing = existingFor(s.id, d.search, d.page);
                            return (
                              <li key={s.id} className="rounded-[10px] border border-[#ececec] bg-[#f8f8f8] p-3.5 text-sm">
                                <div className="flex flex-wrap items-start justify-between gap-2">
                                  <div className="min-w-0 flex-1">
                                    <div className="flex flex-wrap items-center gap-1.5">
                                      {badge ? (
                                        <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${badge.cls}`}>
                                          {badge.label}
                                        </span>
                                      ) : (
                                        <span className="rounded-full bg-[#f1f3f4] px-2.5 py-0.5 text-[10px] font-semibold text-[#4a5560]">
                                          {s.id} · Unconfirmed suggestion
                                        </span>
                                      )}
                                    </div>
                                    <h4 className="mt-1 font-[var(--font-heading)] text-sm font-bold text-[#0a0c0f]">
                                      {s.id === "MC-1" ? "Rewrite the meta for clicks" : s.title}
                                    </h4>
                                  </div>
                                  <div className="flex flex-wrap items-center gap-2">
                                    <ConfirmButton
                                      clientId={client.id}
                                      month={workMonth}
                                      draft={draft}
                                      existing={existing}
                                      onConfirmed={upsertTask}
                                    />
                                    {!existing ? (
                                      <DirectRejectButton
                                        clientId={client.id}
                                        month={workMonth}
                                        kind="suggestion"
                                        ruleId={s.id}
                                        search={d.search}
                                        page={d.page}
                                        title={draft.title}
                                        why={s.why}
                                        steps={s.steps}
                                        reasons={reasons}
                                        onRejected={upsertTask}
                                      />
                                    ) : null}
                                  </div>
                                </div>
                                <p className="mt-1 text-[13px] text-[#4a5560]">{s.why}</p>
                                {s.steps.length > 0 ? (
                                  <div className="mt-2.5 space-y-1.5">
                                    {s.steps.map((step, idx) => {
                                      const isPaa = s.id === "S-2" && /people also ask/i.test(step);
                                      return (
                                        <div key={idx} className="flex items-start gap-2.5 text-[13px] text-[#171a22]">
                                          <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-[#223540] text-[11px] font-bold text-white">
                                            {idx + 1}
                                          </span>
                                          <span className="min-w-0 flex-1">
                                            {isPaa ? (
                                              <span className="mr-1.5 inline-block rounded-full bg-[#e6f7f5] px-2 py-0 text-[10px] font-semibold text-[#00665f]">
                                                PAA
                                              </span>
                                            ) : null}
                                            {step}
                                          </span>
                                        </div>
                                      );
                                    })}
                                  </div>
                                ) : null}
                                {s.needs_to_confirm ? (
                                  <p className="mt-2 text-xs text-[#7a838c]">
                                    <strong className="text-[#4a5560]">Check first:</strong> {s.needs_to_confirm}
                                  </p>
                                ) : null}
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    ) : null}

                    <ChecklistPanel
                      checklist={d.context?.checklist}
                      pageTypeName={d.context?.page_type?.name}
                      focusOrderReason={d.focus_order_reason}
                    />

                    <PageHistoryPanel history={d.page_history} />

                    <GrowthActionPlanner
                      clientId={client.id}
                      month={workMonth}
                      search={d.search}
                      page={d.page}
                      focus={activeDiagFocus}
                      tasks={tasks}
                      rejectionReasons={reasons}
                      onConfirmed={upsertTask}
                    />

                    {d.skipped_suggestions.length > 0 ? (
                      <div className="rounded-xl border border-[#ececec] bg-[#f8f8f8] p-4 text-xs">
                        <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                          Skipped suggestions ({d.skipped_suggestions.length})
                        </div>
                        <ul className="mt-2 space-y-1.5 text-[#4a5560]">
                          {d.skipped_suggestions.map((k) => (
                            <li key={k.id} className="flex flex-wrap items-baseline gap-2">
                              <span className="rounded-full bg-[#f1f3f4] px-2 py-0.5 text-[10px] font-semibold text-[#4a5560]">
                                {k.id}
                              </span>
                              <strong className="text-[#171a22]">{k.name}:</strong>
                              <span>{k.reason}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    {d.not_judged.length > 0 ? (
                      <details className="rounded-xl border border-[#ececec] bg-white px-4 py-3 text-sm">
                        <summary className="cursor-pointer text-xs font-semibold text-[#4a5560]">
                          Rules that did not fire ({d.not_judged.length})
                        </summary>
                        <ul className="mt-2 space-y-1 text-xs text-[#4a5560]">
                          {d.not_judged.map((n) => (
                            <li key={n.action_id}>
                              <strong className="text-[#171a22]">{n.name}:</strong> {n.reason}
                            </li>
                          ))}
                        </ul>
                      </details>
                    ) : null}
                  </>
                )}
              </div>
            );
          })}
        </div>
      ) : null}

      <div id="plan" className="mt-8 scroll-mt-4">
        <EnginePlan
          clientId={client.id}
          month={workMonth}
          tasks={tasks}
          allowance={allowance}
          teamwork={plan.teamwork}
          work={plan.work ?? null}
          team={team}
          onTaskChange={upsertTask}
          rejectionReasons={reasons}
          styleNotes={client.style_notes ?? null}
        />
      </div>
    </section>
  );
}
