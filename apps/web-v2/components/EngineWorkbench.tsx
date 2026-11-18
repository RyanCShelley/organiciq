"use client";

import Link from "next/link";
import { useMemo, useState, useTransition, type CSSProperties, type ReactNode } from "react";

import { buildGrowthActionAction, confirmTaskAction, sendTaskAction, topicForAction, updateTaskAction } from "@/app/(app)/[clientSlug]/engine/actions";
import { assemble } from "@/components/GrowthActionPlanner";
import { Spinner } from "@/components/ui/Spinner";
import type { Allowance, Candidate, EngineTask, GrowthActionBundle, GrowthPart, VisibilityCandidates } from "@/lib/engine";

/**
 * The Decision Engine's Visibility screen as a workbench: opportunities on the left, the diagnosis of the selected
 * search and page on the right, the month's plan in a tray underneath.
 *
 * Three rules hold everywhere on it. The page that was diagnosed stays the page: another page is only ever a
 * suggestion under "Other pages". What the engine could not establish is shown before any task. And when the
 * search's intent was not read, only the tasks that depend on it are held; the rest can still be approved.
 */

type OkBundle = Extract<GrowthActionBundle, { ok: true }>;
type Tone = "ok" | "warn" | "miss" | "info";
type Tab = "tasks" | "evidence" | "serp" | "other";
type Diag = { loading: boolean; bundle: GrowthActionBundle | null; error: string | null };

const TONE: Record<Tone, { bg: string; fg: string; dot: string; border: string }> = {
  ok: { bg: "#e6f7f5", fg: "#00665f", dot: "#00a99d", border: "#bfe9e4" },
  warn: { bg: "oklch(0.97 0.045 85)", fg: "oklch(0.42 0.1 65)", dot: "oklch(0.76 0.15 75)", border: "oklch(0.88 0.08 85)" },
  miss: { bg: "oklch(0.965 0.025 25)", fg: "oklch(0.48 0.17 25)", dot: "oklch(0.62 0.2 25)", border: "oklch(0.88 0.06 25)" },
  info: { bg: "#eef0f1", fg: "#4a5560", dot: "#909a9f", border: "#e3e6e8" },
};
const DARK = "#223540";
const tone = (t: Tone): CSSProperties => ({ background: TONE[t].bg, color: TONE[t].fg, borderColor: TONE[t].border });

const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";
const keyOf = (c: { search: string; page: string }) => `${c.search}|${c.page}`;
const num = (n: number, digits = 0) => n.toLocaleString(undefined, { maximumFractionDigits: digits });
const day = (iso: string | null | undefined) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "");
const daysSince = (iso: string | null | undefined) => (iso ? Math.floor((Date.now() - new Date(`${iso}T00:00:00`).getTime()) / 86_400_000) : null);

const TIERS: { key: Candidate["band"] | null; label: string }[] = [
  { key: null, label: "All" },
  { key: "2-3", label: "Almost #1" },
  { key: "4-10", label: "Near top 3" },
  { key: "11-20", label: "Page 2 → 1" },
];
const SELLING = new Set(["product page", "category or collection page", "service page", "local listing"]);
const EXPLAINING = new Set(["article or blog post", "guide or resource"]);
const CHANNEL: Record<string, string[]> = { SEO: ["Search"], "AI visibility": ["AI answers"], "SEO and AI visibility": ["Search", "AI answers"], Conversion: ["Leads"], "SEO and conversion": ["Search", "Leads"] };
/** A crawl older than this is said on the row: the page may have changed since. */
const STALE_DAYS = 30;

function Pill({ t, children }: { t: Tone; children: ReactNode }) {
  return (
    <span className="inline-block whitespace-nowrap rounded-full border px-[7px] text-[10px] font-semibold leading-[18px]" style={tone(t)}>
      {children}
    </span>
  );
}

/** What a row can say before anyone diagnoses it, and what a diagnosis in this session adds. */
function flagsFor(c: Candidate, diag: Diag | undefined): { t: Tone; text: string }[] {
  const flags: { t: Tone; text: string }[] = [];
  const bundle = diag?.bundle;
  if (bundle && bundle.context && !bundle.context.intent.read) flags.push({ t: "miss", text: "Intent not read" });
  const age = daysSince(c.page_crawled_on);
  if (age != null && age > STALE_DAYS) flags.push({ t: "warn", text: `Page read ${age} days ago` });
  if (c.pages_for_search > 1) flags.push({ t: "warn", text: `${c.pages_for_search} of your pages compete` });
  if (c.strength !== "strong") flags.push({ t: "info", text: "Low volume" });
  return flags;
}

type Verdict = { level: "ready" | "verify" | "held" | "none"; label: string; title: string; story: string; t: Tone };

function verdictOf(b: OkBundle): Verdict {
  const ctx = b.context;
  const held = b.held ?? [];
  const usable = b.parts.length;
  if (b.nothing_recommended) {
    return { level: "none", label: "No action", title: "No action for this page", story: b.nothing_recommended.reason, t: "info" };
  }
  if (ctx && !ctx.intent.read) {
    return {
      level: "held", label: "Partly held", t: "miss",
      title: `Intent not read. ${usable} of ${usable + held.length} task${usable + held.length === 1 ? "" : "s"} can go ahead.`,
      story: ctx.intent.uncertainty || "The results page for this search could not be read, so the engine does not know what searchers want. Tasks that do not depend on that can go ahead.",
    };
  }
  const unverified = ctx?.evidence.unverified ?? [];
  if (unverified.length > 0 || ctx?.validation.verdict === "needs_verification") {
    const n = unverified.length;
    return { level: "verify", label: "Check first", t: "warn", title: n ? `Ready, with ${n} thing${n === 1 ? "" : "s"} to check first` : "Ready, with points to check first", story: ctx?.fit.why ?? "" };
  }
  return { level: "ready", label: "Ready", t: "ok", title: "Ready to approve", story: ctx?.fit.why ?? "" };
}

function chipsOf(b: OkBundle, c: Candidate): { label: string; value: string; sub: string; t: Tone }[] {
  const ctx = b.context;
  if (!ctx) return [];
  const intent = ctx.intent;
  const others = Math.max((b.topic?.pages.length ?? c.pages_for_search) - 1, 0);
  const fitTone: Tone = ctx.fit.level === "high" ? "ok" : ctx.fit.level === "medium" ? "warn" : ctx.fit.level === "low" ? "miss" : "info";
  return [
    { label: "Search intent", value: intent.read ? intent.name : "Intent not read", sub: intent.read ? `${intent.confidence} confidence${intent.serp_date ? `, results page of ${day(intent.serp_date)}` : ""}` : intent.uncertainty ?? "No results page was read", t: intent.read ? (intent.confidence === "high" ? "ok" : "warn") : "miss" },
    { label: "Page fit", value: ctx.fit.level === "unverified" ? "Can't judge yet" : `${ctx.page_type.name}: ${ctx.fit.level === "high" ? "suits the search" : ctx.fit.level === "medium" ? "partial fit" : "does not suit it"}`, sub: ctx.fit.why, t: fitTone },
    { label: "Live page", value: ctx.evidence.source === "live" ? "Read just now" : ctx.evidence.source === "crawl" ? `From the crawl of ${day(ctx.evidence.crawl_date)}` : "Not read", sub: ctx.evidence.summary, t: ctx.evidence.source === "live" ? "ok" : ctx.evidence.source === "crawl" ? "warn" : "miss" },
    { label: "Competing pages", value: others > 0 ? `${others} other${others === 1 ? "" : "s"} of yours rank` : "None", sub: others > 0 ? "More than one of your pages shows for this search" : "Only this page shows for it", t: others > 0 ? "warn" : "ok" },
    { label: "Data volume", value: `${c.strength === "strong" ? "" : "Only "}${num(c.impressions)} impressions`, sub: c.strength === "strong" ? "Three months, reliable" : "The estimate is rough", t: c.strength === "strong" ? "ok" : "warn" },
  ];
}

function LockIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="4" y="11" width="16" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  );
}

export function EngineWorkbench({
  clientId, clientSlug, month, monthName, data, tasks, allowance, teamworkReady, onTaskChange,
}: {
  clientId: string;
  clientSlug: string;
  month: string;
  monthName: string;
  data: VisibilityCandidates;
  tasks: EngineTask[];
  allowance: Allowance;
  teamworkReady: boolean;
  onTaskChange: (task: EngineTask) => void;
}) {
  const [tier, setTier] = useState<Candidate["band"] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [diags, setDiags] = useState<Record<string, Diag>>({});
  const [tab, setTab] = useState<Tab>("tasks");
  const [approved, setApproved] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const [sending, startSend] = useTransition();

  const rows = useMemo(
    () => [...data.candidates].filter((c) => tier === null || c.band === tier).sort((a, b) => b.expected_extra_clicks - a.expected_extra_clicks),
    [data, tier],
  );
  const current = data.candidates.find((c) => keyOf(c) === selected) ?? null;
  const diag = selected ? diags[selected] : undefined;
  const bundle = diag?.bundle && diag.bundle.ok ? diag.bundle : null;

  const planned = tasks.filter((t) => t.kind === "growth_action" && t.status !== "dropped");
  const inPlan = (page: string) => planned.find((t) => t.page === page);
  const slots = Math.max(allowance.monthly ?? 3, planned.length, 1);
  const full = allowance.monthly != null && planned.length >= allowance.monthly;

  function select(key: string) {
    setSelected(key);
    setTab("tasks");
    setExpanded({});
    setMessage(null);
  }

  /** Reads the page and the results page and builds the action. Also what "Read it now" runs: a build always tries the results page again. */
  function diagnose(c: Candidate) {
    const key = keyOf(c);
    setDiags((d) => ({ ...d, [key]: { loading: true, bundle: d[key]?.bundle ?? null, error: null } }));
    void (async () => {
      const topic = await topicForAction(clientId, c.search, c.page);
      if (!topic.ok || !topic.value.keyword) {
        const why = topic.ok ? `${topic.value.source}, so there is no topic to diagnose it under.` : topic.error;
        setDiags((d) => ({ ...d, [key]: { loading: false, bundle: null, error: why } }));
        return;
      }
      const built = await buildGrowthActionAction(clientId, topic.value.keyword, c.page, "visibility", c.page, topic.value.search ?? c.search);
      setDiags((d) => ({ ...d, [key]: { loading: false, bundle: built, error: built.ok ? null : built.error } }));
      if (built.ok) {
        // Approved unless the person says otherwise; optional tasks start unticked; a choice already made is kept.
        setApproved((a) => {
          const next = { ...a };
          built.parts.forEach((p) => (next[`${key}|${p.id}`] = a[`${key}|${p.id}`] ?? true));
          built.optional.forEach((p) => (next[`${key}|${p.id}`] = a[`${key}|${p.id}`] ?? false));
          return next;
        });
      }
    })();
  }

  const selectable = bundle ? [...bundle.parts, ...bundle.optional] : [];
  const chosen = selected ? selectable.filter((p) => approved[`${selected}|${p.id}`]) : [];

  function addToPlan() {
    if (!bundle || !selected || chosen.length === 0) return;
    const choices = Object.fromEntries(selectable.map((p) => [p.id, { on: Boolean(approved[`${selected}|${p.id}`]), editing: false, text: p.steps.join("\n") }]));
    setMessage(null);
    start(async () => {
      const r = await confirmTaskAction(clientId, month, assemble(bundle, selectable, choices));
      if (r.ok) onTaskChange(r.value);
      else setMessage(r.error);
    });
  }

  function remove(task: EngineTask) {
    setMessage(null);
    start(async () => {
      const r = await updateTaskAction(clientId, task.id, { status: "dropped" });
      if (r.ok) onTaskChange(r.value);
      else setMessage(r.error);
    });
  }

  const unsent = planned.filter((t) => !t.teamwork_task_id);
  function sendAll() {
    setMessage(null);
    startSend(async () => {
      for (const task of unsent) {
        const r = await sendTaskAction(clientId, task.id);
        if (r.ok) onTaskChange(r.value);
        else {
          setMessage(`“${task.search}” was not sent: ${r.error}`);
          return;
        }
      }
    });
  }

  function taskCard(p: GrowthPart, held: boolean) {
    const id = `${selected}|${p.id}`;
    const on = !held && Boolean(approved[id]);
    const open = Boolean(expanded[id]);
    const channels = CHANNEL[p.benefit ?? ""] ?? [];
    return (
      <li
        key={p.id}
        className="rounded-[10px] border px-[14px] py-3"
        style={held ? { borderStyle: "dashed", borderColor: TONE.miss.border, background: "#fcfafa" } : { borderColor: on ? "#bfe9e4" : "#e7e7e7", background: "#fff" }}
      >
        <div className="flex items-start gap-3">
          <button
            type="button"
            role="checkbox"
            aria-checked={on}
            aria-label={`Approve: ${p.title}`}
            disabled={held}
            onClick={() => setApproved((a) => ({ ...a, [id]: !a[id] }))}
            className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-[5px] border text-xs font-bold text-white disabled:cursor-not-allowed"
            style={on ? { background: "#00a99d", borderColor: "#00a99d" } : { background: "#fff", borderColor: "#c5cdd2" }}
          >
            {on ? "✓" : ""}
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-bold" style={held ? { color: "#7a838c" } : undefined}>{p.title}</span>
              {channels.map((c) => (
                <span key={c} className="rounded-full px-[7px] text-[10px] font-semibold leading-[18px]" style={{ background: "#e6f7f5", color: "#00665f" }}>{c}</span>
              ))}
              {p.role === "optional" ? <Pill t="info">Optional</Pill> : null}
              {held ? <Pill t="miss">Held: needs intent</Pill> : null}
            </div>
            {p.why ? <p className="mt-0.5 text-[13px] text-[#4a5560]">{p.why}</p> : null}
            {open ? (
              <div className="mt-2 space-y-2 text-[13px]">
                <ul className="space-y-1">
                  {p.steps.map((s) => (
                    <li key={s} className="flex gap-2"><span style={{ color: "#00a99d" }}>→</span><span>{s}</span></li>
                  ))}
                </ul>
                {p.note && p.scope && p.scope !== "page-specific" ? <p className="rounded-lg border px-2 py-1" style={tone("warn")}>{p.scope}: {p.note}</p> : null}
                {p.evidence.length > 0 ? (
                  <button type="button" onClick={() => setTab("evidence")} className="text-xs font-semibold underline" style={{ color: "#00857b" }}>
                    See the {p.evidence.length} signal{p.evidence.length === 1 ? "" : "s"} behind this →
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
          <button type="button" onClick={() => setExpanded((e) => ({ ...e, [id]: !e[id] }))} className="shrink-0 text-xs font-semibold text-[#7a838c]">
            {p.steps.length} step{p.steps.length === 1 ? "" : "s"} {open ? "−" : "+"}
          </button>
        </div>
      </li>
    );
  }

  function diagnosed(c: Candidate, b: OkBundle) {
    const ctx = b.context;
    const v = verdictOf(b);
    const held = b.held ?? [];
    const unverified = ctx?.evidence.unverified ?? [];
    const ranked = ctx?.intent.ranked ?? [];
    const other = b.suggested_page ?? (b.better_page ? { url: b.better_page.url, why: b.better_page.why, next: "Review that page on its own. This action is not moved to it.", exists: true, kind: null, title: null } : null);
    const otherRow = other?.url ? data.candidates.find((x) => x.page === other.url && x.search === c.search) ?? data.candidates.find((x) => x.page === other.url) : undefined;
    const already = inPlan(c.page);
    const tabs: { key: Tab; label: string; badge: ReactNode }[] = [
      { key: "tasks", label: "Recommended tasks", badge: selectable.length ? <Pill t="ok">{chosen.length}/{selectable.length}</Pill> : null },
      { key: "evidence", label: "Evidence", badge: unverified.length ? <Pill t="warn">{unverified.length} unverified</Pill> : null },
      { key: "serp", label: "Results page", badge: ctx && !ctx.intent.read ? <Pill t="miss">Not read</Pill> : null },
      { key: "other", label: "Other pages", badge: other ? <Pill t="info">1</Pill> : null },
    ];
    return (
      <>
        <div className="border-b border-[#e8e8e8] bg-white px-7 pt-[18px]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="font-[family-name:var(--font-display)] text-xl font-bold">“{c.search}”</h2>
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-[#4a5560]">
                <span className="inline-flex items-center gap-1 rounded-md px-[9px] py-[3px] font-semibold text-white" style={{ background: DARK }} title="This diagnosis and its tasks stay on this page">
                  <LockIcon />{shortPage(c.page)}
                </span>
                <span>
                  #{num(c.position, 1)} → <strong style={{ color: "#00857b" }}>#{c.target_position}</strong> · +{num(c.expected_extra_clicks, 1)} clicks / 3 mo · {num(c.impressions)} impressions
                </span>
              </div>
            </div>
            {v.level === "none" ? null : already ? (
              <span className="rounded-full px-[18px] py-2.5 text-[13px] font-semibold" style={{ background: "#e6f7f5", color: "#00665f" }}>In the {monthName} plan ✓</span>
            ) : (
              <button
                type="button"
                onClick={addToPlan}
                disabled={pending || chosen.length === 0 || full}
                className="rounded-full px-[18px] py-2.5 text-[13px] font-semibold text-white"
                style={{ background: pending || chosen.length === 0 || full ? "#c5cdd2" : DARK }}
              >
                {pending ? <><Spinner />Adding…</> : full ? "Plan is full" : `Add ${chosen.length} task${chosen.length === 1 ? "" : "s"} to plan`}
              </button>
            )}
          </div>
          <div className="mt-3 rounded-[10px] border px-[14px] py-3 text-[13px]" style={tone(v.t)}>
            <span className="mr-2 rounded-full bg-white px-2 py-0.5 text-[11px] font-bold uppercase">{v.label}</span>
            <strong>{v.title}</strong>
            {v.story ? <span className="mt-1 block">{v.story}</span> : null}
          </div>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {chipsOf(b, c).map((chip) => (
              <span key={chip.label} title={chip.sub} className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border px-2.5 py-[5px] text-xs" style={tone(chip.t)}>
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: TONE[chip.t].dot }} />
                <span className="text-[#7a838c]">{chip.label}</span>
                <strong>{chip.value}</strong>
              </span>
            ))}
          </div>
          <div className="mt-3 flex gap-[22px]" role="tablist">
            {tabs.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => setTab(t.key)}
                className="flex items-center gap-1.5 border-b-2 pb-2 text-[13px] font-semibold"
                style={tab === t.key ? { color: "#0a0c0f", borderColor: DARK } : { color: "#7a838c", borderColor: "transparent" }}
              >
                {t.label}{t.badge}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2.5 px-7 pb-7 pt-[18px] text-sm">
          {message ? <p role="alert" className="rounded-lg border px-3 py-2 text-[13px]" style={tone("miss")}>{message}</p> : null}

          {tab === "tasks" ? (
            <>
              {held.length > 0 ? (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-dashed px-[14px] py-3 text-[13px]" style={tone("miss")}>
                  <span><strong>Intent not read.</strong> {held.length} task{held.length === 1 ? " is" : "s are"} held until the results page is read.</span>
                  <button type="button" onClick={() => diagnose(c)} disabled={diag?.loading} className="rounded-full border bg-white px-3 py-1 text-xs font-semibold" style={{ borderColor: TONE.miss.border }}>
                    {diag?.loading ? "Reading…" : "Read it now"}
                  </button>
                </div>
              ) : null}
              {v.level === "none" ? (
                <p className="rounded-[10px] border border-[#e7e7e7] bg-white px-[14px] py-3 text-[13px] text-[#4a5560]">
                  Nothing is recommended on this page for this search.{other ? " See Other pages for the page that suits it." : ""}
                </p>
              ) : null}
              <ul className="space-y-2.5">
                {b.parts.map((p) => taskCard(p, false))}
                {b.optional.map((p) => taskCard(p, false))}
                {held.map((p) => taskCard(p, true))}
              </ul>
            </>
          ) : null}

          {tab === "evidence" ? (
            <>
              {unverified.length > 0 ? (
                <div className="rounded-[10px] border bg-white px-[14px] py-3" style={{ borderColor: TONE.warn.border }}>
                  <h3 className="text-[13px] font-bold">Not verified</h3>
                  <ul className="mt-1.5 list-disc space-y-1 pl-5 text-[13px] text-[#4a5560]">{unverified.map((u) => <li key={u}>{u}</li>)}</ul>
                </div>
              ) : null}
              {[...b.parts, ...b.optional, ...held].filter((p) => p.evidence.length > 0).map((p) => (
                <div key={p.id} className="rounded-[10px] border border-[#e7e7e7] bg-white px-[14px] py-3">
                  <h3 className="text-[13px] font-bold">Behind “{p.title}”</h3>
                  <ul className="mt-1.5 space-y-1.5 text-[13px] text-[#4a5560]">{p.evidence.map((e) => <li key={e} className="border-l-2 border-[#e3e6e8] pl-2.5">{e}</li>)}</ul>
                </div>
              ))}
              {ctx?.winners?.llm.ok ? (
                <div className="rounded-[10px] border border-[#e7e7e7] bg-white px-[14px] py-3">
                  <h3 className="text-[13px] font-bold">In AI answers</h3>
                  <p className="mt-1 text-[13px] text-[#4a5560]">Asked “{ctx.winners.llm.prompt}” on {day(ctx.winners.llm.run_date)}.</p>
                  <ul className="mt-1.5 space-y-1.5 text-[13px] text-[#4a5560]">
                    {(ctx.winners.llm.platforms ?? []).map((p) => (
                      <li key={p.platform} className="border-l-2 border-[#e3e6e8] pl-2.5">
                        <strong>{p.platform}:</strong> {p.brand_mentioned ? `named${p.brand_rank ? ` (${p.brand_rank} of ${p.total_brands})` : ""}` : "not named"}, {p.client_cited ? "cited" : "not cited"}
                        {p.brands.length ? `. Named first: ${p.brands.slice(0, 3).join(", ")}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {b.left_out.length > 0 ? (
                <div className="rounded-[10px] border border-[#e7e7e7] bg-white px-[14px] py-3">
                  <h3 className="text-[13px] font-bold">Considered but not included</h3>
                  <ul className="mt-1.5 space-y-1.5 text-[13px] text-[#4a5560]">{b.left_out.map((l) => <li key={l.id}><strong className="text-[#0a0c0f]">{l.name}.</strong> {l.reason}</li>)}</ul>
                </div>
              ) : null}
            </>
          ) : null}

          {tab === "serp" ? (
            ranked.length > 0 ? (
              <div className="overflow-hidden rounded-[10px] border border-[#e7e7e7] bg-white">
                <table className="w-full text-left text-[13px]">
                  <thead className="text-[11px] uppercase tracking-wide text-[#7a838c]">
                    <tr><th className="px-3 py-2 font-semibold">Rank</th><th className="px-3 py-2 font-semibold">Result</th><th className="px-3 py-2 font-semibold">Type</th><th className="px-3 py-2 font-semibold">Signal</th></tr>
                  </thead>
                  <tbody>
                    {ranked.map((r) => (
                      <tr key={`${r.rank}-${r.url}`} className="border-t border-[#f1f2f3]">
                        <td className="px-3 py-2 tabular-nums">{r.rank}</td>
                        <td className="px-3 py-2"><span className="font-semibold">{r.title || r.domain}</span><span className="block text-[11px] text-[#7a838c]">{r.domain}</span></td>
                        <td className="px-3 py-2 text-[#4a5560]">{r.content_type ?? "Not established"}</td>
                        <td className="px-3 py-2">
                          {SELLING.has(r.content_type ?? "") ? <span className="rounded-full px-[7px] text-[10px] font-semibold leading-[18px]" style={{ background: "#e9fedc", color: "#2f5a00" }}>Buying</span>
                            : EXPLAINING.has(r.content_type ?? "") ? <Pill t="info">Researching</Pill> : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="rounded-[10px] border border-dashed px-[14px] py-3 text-[13px]" style={tone("miss")}>
                The results page for this search was not read{ctx?.intent.uncertainty ? `: ${ctx.intent.uncertainty}` : "."}
              </p>
            )
          ) : null}

          {tab === "other" ? (
            other ? (
              <>
                <div className="rounded-[10px] border border-[#e7e7e7] bg-white px-[14px] py-3">
                  {other.url ? <div className="break-all font-bold">{shortPage(other.url)}</div> : <div className="font-bold">No page of the right kind on this site</div>}
                  <p className="mt-1 text-[13px] text-[#4a5560]">{other.why}</p>
                  {otherRow ? (
                    <button type="button" onClick={() => select(keyOf(otherRow))} className="mt-2 rounded-full border border-[#c5cdd2] px-3 py-1 text-xs font-semibold hover:bg-[#e6f7f5]">Open in the list</button>
                  ) : other.url ? <p className="mt-2 text-xs text-[#7a838c]">That page is not among this list&apos;s opportunities, so it has no row to open.</p> : null}
                </div>
                <p className="text-xs text-[#7a838c]">Suggestions only. This diagnosis and its tasks stay on {shortPage(c.page)}.</p>
              </>
            ) : <p className="text-[13px] text-[#7a838c]">No other page of this site suits this search better. This diagnosis stays on {shortPage(c.page)}.</p>
          ) : null}
        </div>
      </>
    );
  }

  return (
    <div className="flex h-[calc(100vh-15.5rem)] min-h-[34rem] overflow-hidden rounded-xl border border-[#e8e8e8] text-sm" style={{ background: "#f6f7f7" }}>
      <aside className="flex w-[390px] shrink-0 flex-col border-r border-[#e8e8e8] bg-white">
        <div className="px-4 pb-2.5 pt-3.5">
          <div className="flex items-baseline justify-between">
            <h2 className="font-[family-name:var(--font-display)] text-base font-bold">Opportunities</h2>
            <span className="text-xs text-[#7a838c]">{num(data.counts.found)} in reach · by potential</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {TIERS.map((t) => (
              <button
                key={t.label}
                type="button"
                aria-pressed={tier === t.key}
                onClick={() => setTier(t.key)}
                className="rounded-full border px-2.5 py-1 text-[11px] font-semibold"
                style={tier === t.key ? { background: DARK, color: "#fff", borderColor: DARK } : { background: "#fff", borderColor: "#e3e6e8" }}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
        <ul className="flex-1 overflow-y-auto">
          {rows.map((c) => {
            const key = keyOf(c);
            const d = diags[key];
            const state = inPlan(c.page) ? "#00a99d" : d?.bundle ? DARK : "#d3d7d9";
            const flags = flagsFor(c, d);
            return (
              <li key={key}>
                <button
                  type="button"
                  onClick={() => select(key)}
                  aria-current={selected === key}
                  className="block w-full border-b border-[#f1f2f3] px-4 py-3 text-left hover:bg-[#f8f8f8]"
                  style={selected === key ? { background: "#eef8f7", boxShadow: "inset 0 0 0 1.5px #00a99d" } : undefined}
                >
                  <div className="flex items-start gap-2.5">
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: state }} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-[13px] font-semibold text-[#0a0c0f]">{c.search}</span>
                        <span className="font-[family-name:var(--font-display)] text-sm font-bold tabular-nums">+{num(c.expected_extra_clicks, 1)}</span>
                      </div>
                      <div className="mt-0.5 flex items-baseline justify-between gap-2 text-[11px] text-[#7a838c]">
                        <span className="truncate">{shortPage(c.page)}</span>
                        <span className="shrink-0 tabular-nums">#{num(c.position, 1)} → #{c.target_position}</span>
                      </div>
                      {flags.length > 0 ? <div className="mt-1.5 flex flex-wrap gap-1">{flags.map((f) => <Pill key={f.text} t={f.t}>{f.text}</Pill>)}</div> : null}
                    </div>
                  </div>
                </button>
              </li>
            );
          })}
          {rows.length === 0 ? <li className="px-4 py-6 text-[13px] text-[#7a838c]">Nothing in this tier for this scope.</li> : null}
        </ul>
        <div className="flex gap-3 border-t border-[#f1f2f3] px-4 py-2 text-xs text-[#7a838c]">
          {[["#d3d7d9", "Not reviewed"], [DARK, "Diagnosed"], ["#00a99d", "In plan"]].map(([color, label]) => (
            <span key={label} className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: color }} />{label}</span>
          ))}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto">
          {!current ? (
            <div className="flex h-full flex-col items-center justify-center px-8 text-center">
              <h2 className="font-[family-name:var(--font-display)] text-xl font-bold">Pick a search to diagnose</h2>
              <p className="mt-2 max-w-md text-[#4a5560]">The engine reads the page live, checks the results page and your other pages, then gives a verdict with the tasks it recommends.</p>
            </div>
          ) : diag?.loading && !bundle ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-[#4a5560]">
              <span className="h-[30px] w-[30px] animate-spin rounded-full border-[3px] border-[#e3e6e8]" style={{ borderTopColor: "#00a99d" }} />
              Reading the page live and checking the results page…
            </div>
          ) : bundle ? (
            diagnosed(current, bundle)
          ) : (
            <div className="px-7 py-6">
              <h2 className="font-[family-name:var(--font-display)] text-[22px] font-bold">“{current.search}”</h2>
              <p className="mt-1 text-xs text-[#4a5560]">
                {shortPage(current.page)} · #{num(current.position, 1)} → #{current.target_position} · +{num(current.expected_extra_clicks, 1)} clicks / 3 mo · {num(current.impressions)} impressions
              </p>
              <div className="mt-2 flex flex-wrap gap-1">{flagsFor(current, diag).map((f) => <Pill key={f.text} t={f.t}>{f.text}</Pill>)}</div>
              {diag?.error ? <p role="alert" className="mt-4 max-w-[560px] rounded-[10px] border px-[14px] py-3 text-[13px]" style={tone("miss")}>{diag.error}</p> : null}
              <div className="mt-4 max-w-[560px] rounded-xl border border-[#e7e7e7] bg-white p-5">
                <p className="text-[#4a5560]">A diagnosis takes about 20 seconds. It checks:</p>
                <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
                  {["The live page and its content", "What searchers want (intent)", "Who ranks above you, and why", "Your other pages that compete"].map((item) => (
                    <li key={item} className="flex gap-2"><span style={{ color: "#00a99d" }}>→</span>{item}</li>
                  ))}
                </ul>
                <button type="button" onClick={() => diagnose(current)} className="mt-4 rounded-full px-[18px] py-2.5 text-[13px] font-semibold text-white" style={{ background: DARK }}>
                  {diag?.error ? "Try again" : "Diagnose this page"}
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 border-t border-[#e8e8e8] bg-white px-5 py-2.5">
          <div className="shrink-0">
            <div className="font-[family-name:var(--font-display)] text-[13px] font-bold">{monthName} plan</div>
            <div className="text-[11px] text-[#7a838c]">{planned.length}{allowance.monthly != null ? ` of ${allowance.monthly}` : ""} action{planned.length === 1 && allowance.monthly == null ? "" : "s"}</div>
          </div>
          <div className="flex min-w-0 flex-1 gap-2 overflow-x-auto">
            {Array.from({ length: slots }, (_, i) => planned[i]).map((task, i) =>
              task ? (
                <div key={task.id} className="flex min-h-[42px] min-w-[10rem] flex-1 items-center gap-2 rounded-lg border px-2.5 py-1" style={{ borderColor: "#bfe9e4" }}>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-semibold">{task.search}</div>
                    <div className="truncate text-[11px] text-[#7a838c]">{task.parts?.length ?? 1} task{(task.parts?.length ?? 1) === 1 ? "" : "s"} · {shortPage(task.page)}{task.teamwork_task_id ? " · sent" : ""}</div>
                  </div>
                  {task.teamwork_task_id ? null : <button type="button" onClick={() => remove(task)} disabled={pending} aria-label={`Remove ${task.search} from the plan`} className="text-[#7a838c] hover:text-red-700">×</button>}
                </div>
              ) : (
                <div key={`open-${i}`} className="flex min-h-[42px] min-w-[10rem] flex-1 items-center justify-center rounded-lg border border-dashed border-[#d3d7d9] bg-[#f8f8f8] text-xs text-[#7a838c]">Open slot</div>
              ),
            )}
          </div>
          <Link href={`/${clientSlug}/engine#plan`} className="shrink-0 text-xs font-semibold underline" style={{ color: "#00857b" }}>Assign and track ↓</Link>
          <button
            type="button"
            onClick={sendAll}
            disabled={sending || unsent.length === 0 || !teamworkReady}
            title={teamworkReady ? undefined : "Teamwork is not set up for this client. Choose a tasklist in Settings → Connections."}
            className="shrink-0 rounded-full px-[18px] py-2.5 text-[13px] font-semibold text-white"
            style={{ background: planned.length > 0 && unsent.length === 0 ? "#00a99d" : sending || unsent.length === 0 || !teamworkReady ? "#c5cdd2" : DARK }}
          >
            {sending ? <><Spinner />Sending…</> : planned.length > 0 && unsent.length === 0 ? "Sent to Teamwork ✓" : "Send to Teamwork"}
          </button>
        </div>
      </div>
    </div>
  );
}
