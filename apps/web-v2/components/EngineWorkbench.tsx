"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, useTransition, type ReactNode } from "react";

import {
  buildGrowthActionAction,
  confirmTaskAction,
  diagnosePagesAction,
  pageHistoryAction,
  pullSerpAction,
  rejectTaskAction,
  sendTaskAction,
  serpLookupAction,
  topicForAction,
  updateTaskAction,
} from "@/app/(app)/[clientSlug]/engine/actions";
import { ChecklistTab } from "@/components/engine-workbench/ChecklistTab";
import { FaqEvidenceCard } from "@/components/engine-workbench/FaqEvidenceCard";
import { HistoryTab } from "@/components/engine-workbench/HistoryTab";
import { SerpTab } from "@/components/engine-workbench/SerpTab";
import {
  DARK,
  Pill,
  PriorRejectionsCard,
  RejectForm,
  StyleNotesBanner,
  TEAL,
  TONE,
  daysSince,
  formatDay,
  num,
  shortPage,
  toneStyle,
  type Tone,
} from "@/components/engine-workbench/tokens";
import { Spinner } from "@/components/ui/Spinner";
import {
  REJECTION_REASONS,
  type Allowance,
  type Candidate,
  type Diagnosis,
  type DroppedPage,
  type EngineKind,
  type EngineTask,
  type GrowthActionBundle,
  type GrowthPart,
  type LeadRow,
  type LeadsCandidates,
  type PageHistory,
  type PriorRejection,
  type RejectionReason,
  type SerpLookupResult,
  type TaskDraft,
  type TrafficCandidates,
  type VisibilityCandidates,
} from "@/lib/engine";

/**
 * The Decision Engine's Visibility workbench: opportunities on the left, the diagnosis of the selected
 * search and page on the right, the month's plan in a tray underneath.
 *
 * Three rules hold everywhere on it. The page that was diagnosed stays the page: another page is only ever a
 * suggestion under "Other pages". What the engine could not establish is shown before any task. And when the
 * search's intent was not read, only the tasks that depend on it are held; the rest can still be approved.
 */

type OkBundle = Extract<GrowthActionBundle, { ok: true }>;
type Tab = "tasks" | "checklist" | "evidence" | "serp" | "history" | "other";
type Diag = { loading: boolean; bundle: GrowthActionBundle | null; fallback?: Diagnosis | null; error: string | null };
type SerpEntry = { loading: boolean; pulling: boolean; data: SerpLookupResult | null; error: string | null };
type HistoryEntry = { loading: boolean; data: PageHistory | null; error: string | null };
type CustomPart = GrowthPart & { uid: string; custom: true };

type WorkbenchItem = {
  key: string;
  kind: EngineKind;
  search: string;
  page: string;
  title: string;
  subtitle: string;
  rightMetric: string;
  rightSubMetric: string;
  tierKey: string;
  sortValue: number;
  candidate?: Candidate;
  trafficRow?: DroppedPage;
  leadRow?: LeadRow;
};

const TIERS_BY_FOCUS: Record<EngineKind, { key: string | null; label: string }[]> = {
  visibility: [
    { key: null, label: "All" },
    { key: "2-3", label: "Almost #1" },
    { key: "4-10", label: "Near top 3" },
    { key: "11-20", label: "Page 2 → 1" },
  ],
  traffic: [
    { key: null, label: "All" },
    { key: "sudden", label: "Sudden" },
    { key: "slow_bleed", label: "Slow bleed" },
    { key: "both", label: "Both" },
  ],
  leads: [
    { key: null, label: "All" },
    { key: "worst_conversion", label: "Low conv." },
    { key: "worst_engagement", label: "Low engage." },
    { key: "both", label: "Both" },
  ],
};
const CHANNEL: Record<string, string[]> = {
  SEO: ["Search"],
  "AI visibility": ["AI answers"],
  "SEO and AI visibility": ["Search", "AI answers"],
  Conversion: ["Leads"],
  "SEO and conversion": ["Search", "Leads"],
};
const READY_CHECKS: Record<EngineKind, string[]> = {
  visibility: [
    "The live page, checklist, and change history",
    "What searchers want (intent & SERP features)",
    "Who ranks above you and People Also Ask",
    "Your other pages that compete for this term",
  ],
  traffic: [
    "The live page, checklist, and change history",
    "Which searches on this page lost the most clicks",
    "Whether search demand fell or rankings slipped",
    "Indexability, canonical, and title/meta CTR signals",
  ],
  leads: [
    "The live page, checklist, and change history",
    "Conversion elements, CTAs, and form friction",
    "In-content links to your conversion pages",
    "Engagement and conversion rate against your site's norm",
  ],
};

const LOADING_COPY: Record<EngineKind, string> = {
  visibility: "Reading the page live and checking the results page…",
  traffic: "Reading the page live and checking why traffic dropped…",
  leads: "Reading the page live and checking conversion paths…",
};

const FOCUS_LABEL: Record<EngineKind, string> = {
  visibility: "Visibility",
  traffic: "Traffic",
  leads: "Leads",
};
/** A crawl older than this is said on the row: the page may have changed since. */
const STALE_DAYS = 30;

const keyOf = (c: { search: string; page: string }) => `${c.search}|${c.page}`;

function partStateKey(selectionKey: string, p: GrowthPart & { uid?: string }): string {
  return `${selectionKey}|${p.uid ?? p.id}`;
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "–";
  if (Math.abs(v) < 1) return "flat";
  return `${v > 0 ? "▲" : "▼"} ${Math.abs(v).toFixed(0)}%`;
}

function findInitialItemKey(items: WorkbenchItem[], initialTerm: string | null | undefined): string | null {
  const needle = (initialTerm ?? "").trim().toLowerCase();
  if (!needle) return null;
  const exact = items.find((c) => c.search.trim().toLowerCase() === needle || c.page.toLowerCase() === needle);
  if (exact) return exact.key;
  const partial = items.find((c) => c.search.trim().toLowerCase().includes(needle) || c.page.toLowerCase().includes(needle));
  return partial ? partial.key : null;
}

/** What a row can say before anyone diagnoses it, and what a diagnosis in this session adds. */
function flagsFor(item: WorkbenchItem, diag: Diag | undefined): { t: Tone; text: string }[] {
  const flags: { t: Tone; text: string }[] = [];
  const bundle = diag?.bundle;
  if (bundle && bundle.context && !bundle.context.intent.read) flags.push({ t: "miss", text: "Intent not read" });
  if (item.candidate) {
    const c = item.candidate;
    const age = daysSince(c.page_crawled_on);
    if (age != null && age > STALE_DAYS) flags.push({ t: "warn", text: `Page read ${age} days ago` });
    if (c.pages_for_search > 1) flags.push({ t: "warn", text: `${c.pages_for_search} of your pages compete` });
    if (c.strength !== "strong") flags.push({ t: "info", text: "Low volume" });
  } else if (item.trafficRow) {
    const p = item.trafficRow;
    if (p.flag === "both") flags.push({ t: "miss", text: "Sudden & slow bleed" });
    else if (p.flag === "sudden") flags.push({ t: "warn", text: "Sudden drop" });
    else if (p.flag === "slow_bleed") flags.push({ t: "warn", text: "Slow bleed" });
  } else if (item.leadRow) {
    const l = item.leadRow;
    if (l.worst_conversion) flags.push({ t: "miss", text: "Low conversion" });
    if (l.worst_engagement) flags.push({ t: "warn", text: "Low engagement" });
    if (l.strength !== "strong") flags.push({ t: "info", text: "Possible" });
  }
  return flags;
}

type Verdict = { level: "ready" | "verify" | "held" | "none"; label: string; title: string; story: string; t: Tone };

function verdictOf(b: OkBundle, customCount: number): Verdict {
  const ctx = b.context;
  const held = b.held ?? [];
  const usable = b.parts.length;
  if (b.nothing_recommended && customCount === 0) {
    return { level: "none", label: "No action", title: "No action for this page", story: b.nothing_recommended.reason, t: "info" };
  }
  if (ctx && !ctx.intent.read) {
    return {
      level: "held",
      label: "Partly held",
      t: "miss",
      title: `Intent not read. ${usable} of ${usable + held.length} task${usable + held.length === 1 ? "" : "s"} can go ahead.`,
      story:
        ctx.intent.uncertainty ||
        "The results page for this search could not be read, so the engine does not know what searchers want. Tasks that do not depend on that can go ahead.",
    };
  }
  const unverified = ctx?.evidence.unverified ?? [];
  if (unverified.length > 0 || ctx?.validation.verdict === "needs_verification") {
    const n = unverified.length;
    return {
      level: "verify",
      label: "Check first",
      t: "warn",
      title: n ? `Ready, with ${n} thing${n === 1 ? "" : "s"} to check first` : "Ready, with points to check first",
      story: ctx?.fit.why ?? "",
    };
  }
  return { level: "ready", label: "Ready", t: "ok", title: "Ready to approve", story: ctx?.fit.why ?? "" };
}

function chipsOf(b: OkBundle, item: WorkbenchItem): { label: string; value: string; sub: string; t: Tone }[] {
  const ctx = b.context;
  if (!ctx) return [];
  const intent = ctx.intent;
  const others = Math.max((b.topic?.pages.length ?? item.candidate?.pages_for_search ?? 1) - 1, 0);
  const fitTone: Tone = ctx.fit.level === "high" ? "ok" : ctx.fit.level === "medium" ? "warn" : ctx.fit.level === "low" ? "miss" : "info";
  const impressions = item.candidate?.impressions ?? b.chosen.impressions;
  const strong = item.candidate ? item.candidate.strength === "strong" : impressions >= 100;
  return [
    {
      label: "Search intent",
      value: intent.read ? intent.name : "Intent not read",
      sub: intent.read
        ? `${intent.confidence} confidence${intent.serp_date ? `, results page of ${formatDay(intent.serp_date)}` : ""}`
        : intent.uncertainty ?? "No results page was read",
      t: intent.read ? (intent.confidence === "high" ? "ok" : "warn") : "miss",
    },
    {
      label: "Page fit",
      value:
        ctx.fit.level === "unverified"
          ? "Can't judge yet"
          : `${ctx.page_type.name}: ${ctx.fit.level === "high" ? "suits the search" : ctx.fit.level === "medium" ? "partial fit" : "does not suit it"}`,
      sub: ctx.fit.why,
      t: fitTone,
    },
    {
      label: "Live page",
      value:
        ctx.evidence.source === "live"
          ? "Read just now"
          : ctx.evidence.source === "crawl"
            ? `From the crawl of ${formatDay(ctx.evidence.crawl_date)}`
            : "Not read",
      sub: ctx.evidence.summary,
      t: ctx.evidence.source === "live" ? "ok" : ctx.evidence.source === "crawl" ? "warn" : "miss",
    },
    {
      label: "Competing pages",
      value: others > 0 ? `${others} other${others === 1 ? "" : "s"} of yours rank` : "None",
      sub: others > 0 ? "More than one of your pages shows for this search" : "Only this page shows for it",
      t: others > 0 ? "warn" : "ok",
    },
    {
      label: "Data volume",
      value: `${strong ? "" : "Only "}${num(impressions)} impressions`,
      sub: strong ? "Three months, reliable" : "The estimate is rough",
      t: strong ? "ok" : "warn",
    },
  ];
}

function buildWorkbenchDraft(
  bundle: OkBundle,
  selectionKey: string,
  chosenParts: (GrowthPart & { uid?: string })[],
  allSelectable: (GrowthPart & { uid?: string })[],
  approvedMap: Record<string, boolean>,
  stepTexts: Record<string, string>,
): TaskDraft {
  const steps: string[] = [];
  chosenParts.forEach((p, i) => {
    const sk = partStateKey(selectionKey, p);
    const raw = stepTexts[sk] ?? p.steps.join("\n");
    steps.push(`# ${i + 1}. ${p.name}`);
    steps.push(
      ...raw
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean),
    );
  });

  const baseDraft: TaskDraft = bundle.draft ?? {
    kind: "growth_action",
    rule_id: "GA",
    search: bundle.keyword,
    page: bundle.page,
    title: `Growth action: ${shortPage(bundle.page)} for “${bundle.keyword}”`,
    why: null,
    steps: [],
    done_when: "Every part above is live on the page.",
    metric: `Clicks and impressions for searches containing “${bundle.keyword}” in Search Console`,
    effort_min: null,
    evidence: [],
  };

  const droppedPrefixes = allSelectable
    .filter((p) => !approvedMap[partStateKey(selectionKey, p)])
    .map((p) => `${p.name}: `);
  const addedEvidence = chosenParts
    .filter((p) => !bundle.parts.some((b) => b.id === p.id))
    .flatMap((p) => p.evidence.map((e) => `${p.name}: ${e}`));
  const evidence = [
    ...baseDraft.evidence.filter((e) => !droppedPrefixes.some((d) => e.startsWith(d))),
    ...addedEvidence,
  ].filter(Boolean);

  const isInvestigation = bundle.parts.some((p) => p.id === "TI-1");
  return {
    ...baseDraft,
    why: isInvestigation
      ? baseDraft.why
      : `This page gets the most impressions for “${bundle.keyword}” (${bundle.chosen.impressions.toLocaleString()} over three months). The work is ${chosenParts.length} part${chosenParts.length === 1 ? "" : "s"}, done together on this one page: ${chosenParts.map((p) => p.name.toLowerCase()).join(", ")}.`,
    steps,
    evidence,
    parts: chosenParts.map((p) => ({
      id: p.custom ? "CUSTOM" : p.id,
      name: p.name,
      ...(p.custom ? { custom: true } : {}),
    })),
  };
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
  clientId,
  clientSlug,
  month,
  monthName,
  data,
  traffic,
  leads,
  tasks,
  allowance,
  teamworkReady,
  onTaskChange,
  focus = "visibility",
  rejectionReasons = REJECTION_REASONS,
  styleNotes,
  initialTerm,
}: {
  clientId: string;
  clientSlug: string;
  month: string;
  monthName: string;
  data?: VisibilityCandidates | null;
  traffic?: TrafficCandidates | null;
  leads?: LeadsCandidates | null;
  tasks: EngineTask[];
  allowance: Allowance;
  teamworkReady: boolean;
  onTaskChange: (task: EngineTask) => void;
  focus?: EngineKind;
  rejectionReasons?: RejectionReason[];
  styleNotes?: string | null;
  initialTerm?: string | null;
}) {
  const activeFocus: EngineKind = focus ?? "visibility";
  const items = useMemo<WorkbenchItem[]>(() => {
    if (activeFocus === "traffic") {
      return (traffic?.dropped_pages ?? []).map((p) => ({
        key: `traffic|${p.page}`,
        kind: "traffic",
        search: "",
        page: p.page,
        title: shortPage(p.page),
        subtitle: `Mo: ${num(p.sessions.current)} (${fmtPct(p.sessions.change_pct)}) · 3m: ${num(p.three_months.current)} (${fmtPct(p.three_months.change_pct)})`,
        rightMetric: `-${num(p.lost_month)}`,
        rightSubMetric: "lost / mo",
        tierKey: p.flag ?? "other",
        sortValue: p.lost_month,
        trafficRow: p,
      }));
    }
    if (activeFocus === "leads") {
      const nounPlural = leads?.noun.plural ?? "conversions";
      return (leads?.candidates ?? []).map((l) => ({
        key: `leads|${l.page}`,
        kind: "leads",
        search: "",
        page: l.page,
        title: shortPage(l.page),
        subtitle: `${num(l.sessions)} sessions · ${num(l.conversions)} ${nounPlural} (${l.conversion_rate.toFixed(1)}%)`,
        rightMetric: `+${num(l.missed_conversions, 1)}`,
        rightSubMetric: `${l.conversion_rate.toFixed(1)}% conv`,
        tierKey: l.worst_conversion && l.worst_engagement ? "both" : l.worst_conversion ? "worst_conversion" : l.worst_engagement ? "worst_engagement" : "other",
        sortValue: l.missed_conversions,
        leadRow: l,
      }));
    }
    return (data?.candidates ?? []).map((c) => ({
      key: keyOf(c),
      kind: "visibility",
      search: c.search,
      page: c.page,
      title: c.search,
      subtitle: shortPage(c.page),
      rightMetric: `+${num(c.expected_extra_clicks, 1)}`,
      rightSubMetric: `#${num(c.position, 1)} → #${c.target_position}`,
      tierKey: c.band,
      sortValue: c.expected_extra_clicks,
      candidate: c,
    }));
  }, [activeFocus, data, traffic, leads]);

  const [query, setQuery] = useState("");
  const [tier, setTier] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(() => findInitialItemKey(items, initialTerm));
  const [diags, setDiags] = useState<Record<string, Diag>>({});
  const [tab, setTab] = useState<Tab>("tasks");
  const [approved, setApproved] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [editingPart, setEditingPart] = useState<Record<string, boolean>>({});
  const [stepTexts, setStepTexts] = useState<Record<string, string>>({});
  const [customByKey, setCustomByKey] = useState<Record<string, CustomPart[]>>({});
  const [addingCustom, setAddingCustom] = useState(false);
  const [customTitle, setCustomTitle] = useState("");
  const [customBody, setCustomBody] = useState("");

  const [rejectOpen, setRejectOpen] = useState(false);
  const [sessionRejections, setSessionRejections] = useState<Record<string, PriorRejection[]>>({});
  const [serpBySearch, setSerpBySearch] = useState<Record<string, SerpEntry>>({});
  const [serpQueryBySel, setSerpQueryBySel] = useState<Record<string, string>>({});
  const [historyByPage, setHistoryByPage] = useState<Record<string, HistoryEntry>>({});

  const [message, setMessage] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const [sending, startSend] = useTransition();

  useEffect(() => {
    const match = findInitialItemKey(items, initialTerm);
    setSelected(match);
    setTier(null);
    setQuery("");
    setTab("tasks");
    setRejectOpen(false);
    setMessage(null);
    setFeedback(null);
  }, [activeFocus, initialTerm, items]);

  const nonRejectedTaskIds = useMemo(
    () => new Set(tasks.filter((t) => t.status !== "rejected").map((t) => t.id)),
    [tasks],
  );

  useEffect(() => {
    if (nonRejectedTaskIds.size === 0) return;
    setSessionRejections((prev) => {
      let changed = false;
      const next: Record<string, PriorRejection[]> = {};
      for (const [pageKey, list] of Object.entries(prev)) {
        const filtered = list.filter((sr) => !nonRejectedTaskIds.has(sr.id));
        if (filtered.length !== list.length) changed = true;
        if (filtered.length > 0) next[pageKey] = filtered;
      }
      return changed ? next : prev;
    });
  }, [nonRejectedTaskIds]);

  const sortedAll = useMemo(
    () => [...items].sort((a, b) => b.sortValue - a.sortValue),
    [items],
  );

  const needle = query.trim().toLowerCase();
  const searchFiltered = useMemo(
    () =>
      needle
        ? sortedAll.filter((c) => c.title.toLowerCase().includes(needle) || c.page.toLowerCase().includes(needle))
        : sortedAll,
    [sortedAll, needle],
  );

  const activeTiers = TIERS_BY_FOCUS[activeFocus];
  const tierCounts = useMemo(() => {
    const counts: Record<string, number> = { all: searchFiltered.length };
    searchFiltered.forEach((c) => {
      counts[c.tierKey] = (counts[c.tierKey] ?? 0) + 1;
    });
    return counts;
  }, [searchFiltered]);

  const rows = useMemo(
    () => (tier === null ? searchFiltered : searchFiltered.filter((c) => c.tierKey === tier)),
    [searchFiltered, tier],
  );

  const current = items.find((c) => c.key === selected) ?? null;
  const diag = selected ? diags[selected] : undefined;
  const bundle = diag?.bundle && diag.bundle.ok ? diag.bundle : null;
  const fallbackDiag = diag?.fallback ?? null;

  const planned = tasks.filter(
    (t) => t.kind === "growth_action" && t.status !== "dropped" && t.status !== "rejected",
  );
  const inPlan = (page: string) => planned.find((t) => t.page === page);
  const slots = Math.max(allowance.monthly ?? 3, planned.length, 1);
  const full = allowance.monthly != null && planned.length >= allowance.monthly;

  function select(key: string) {
    setSelected(key);
    setTab("tasks");
    setExpanded({});
    setEditingPart({});
    setAddingCustom(false);
    setRejectOpen(false);
    setMessage(null);
    setFeedback(null);
  }

  function loadSerp(searchText: string, forcePull = false) {
    const normSearch = searchText.trim().toLowerCase();
    if (!normSearch) return;
    setSerpBySearch((prev) => ({
      ...prev,
      [normSearch]: {
        loading: !forcePull,
        pulling: forcePull,
        data: prev[normSearch]?.data ?? null,
        error: null,
      },
    }));
    void (async () => {
      const r = forcePull
        ? await pullSerpAction(clientId, normSearch)
        : await serpLookupAction(clientId, normSearch, false);
      setSerpBySearch((prev) => ({
        ...prev,
        [normSearch]: {
          loading: false,
          pulling: false,
          data: r.ok ? r.value : (prev[normSearch]?.data ?? null),
          error: r.ok ? null : r.error,
        },
      }));
    })();
  }

  function loadPageHistory(pageUrl: string) {
    setHistoryByPage((prev) => ({
      ...prev,
      [pageUrl]: { loading: true, data: prev[pageUrl]?.data ?? null, error: null },
    }));
    void (async () => {
      const r = await pageHistoryAction(clientId, pageUrl);
      setHistoryByPage((prev) => ({
        ...prev,
        [pageUrl]: {
          loading: false,
          data: r.ok ? r.value : (prev[pageUrl]?.data ?? null),
          error: r.ok ? null : r.error,
        },
      }));
    })();
  }

  /** Reads the page and builds the diagnosis. Visibility uses the keyword/SERP growth-action pipeline; Traffic & Leads diagnose the page directly. */
  function diagnose(item: WorkbenchItem) {
    const key = item.key;
    setDiags((d) => ({
      ...d,
      [key]: { loading: true, bundle: d[key]?.bundle ?? null, fallback: d[key]?.fallback ?? null, error: null },
    }));
    setRejectOpen(false);
    setMessage(null);
    setFeedback(null);
    void (async () => {
      if (activeFocus === "traffic" || activeFocus === "leads") {
        const res = await diagnosePagesAction(clientId, activeFocus, [item.page]);
        if (!res.ok || !res.results[0]) {
          const err = res.ok ? "The page could not be diagnosed." : res.error;
          setDiags((d) => ({ ...d, [key]: { loading: false, bundle: null, fallback: null, error: err } }));
          return;
        }
        const fb = res.results[0];
        setDiags((d) => ({ ...d, [key]: { loading: false, bundle: null, fallback: fb, error: null } }));
        const fbParts = [
          ...fb.prescriptions.map((p) => ({ id: p.action_id, steps: p.steps, core: true })),
          ...fb.suggestions.map((s) => ({ id: s.id, steps: s.steps, core: true })),
        ];
        setApproved((a) => {
          const next = { ...a };
          fbParts.forEach((p) => {
            const k = `${key}|${p.id}`;
            next[k] = a[k] ?? p.core;
          });
          return next;
        });
        setStepTexts((s) => {
          const next = { ...s };
          fbParts.forEach((p) => {
            const k = `${key}|${p.id}`;
            if (next[k] === undefined) next[k] = p.steps.join("\n");
          });
          return next;
        });
        if (fb.page_history) {
          setHistoryByPage((prev) => ({
            ...prev,
            [fb.page]: { loading: false, data: fb.page_history ?? null, error: null },
          }));
        }
        return;
      }

      const topic = await topicForAction(clientId, item.search, item.page);
      if (!topic.ok || !topic.value.keyword) {
        const why = topic.ok ? `${topic.value.source}, so there is no topic to diagnose it under.` : topic.error;
        setDiags((d) => ({ ...d, [key]: { loading: false, bundle: null, fallback: null, error: why } }));
        return;
      }
      const built = await buildGrowthActionAction(
        clientId,
        topic.value.keyword,
        item.page,
        activeFocus,
        item.page,
        topic.value.search ?? item.search,
      );
      setDiags((d) => ({ ...d, [key]: { loading: false, bundle: built, fallback: null, error: built.ok ? null : built.error } }));
      if (built.ok) {
        setApproved((a) => {
          const next = { ...a };
          built.parts.forEach((p) => {
            const k = partStateKey(key, p);
            next[k] = a[k] ?? true;
          });
          built.optional.forEach((p) => {
            const k = partStateKey(key, p);
            next[k] = a[k] ?? false;
          });
          return next;
        });
        setStepTexts((s) => {
          const next = { ...s };
          [...built.parts, ...built.optional].forEach((p) => {
            const k = partStateKey(key, p);
            if (next[k] === undefined) next[k] = p.steps.join("\n");
          });
          return next;
        });
        const serpSearch = built.search || item.search;
        if (serpSearch.trim()) {
          setSerpQueryBySel((prev) => ({ ...prev, [key]: serpSearch.trim().toLowerCase() }));
          loadSerp(serpSearch, false);
        }
        if (built.page_history) {
          setHistoryByPage((prev) => ({
            ...prev,
            [built.page]: { loading: false, data: built.page_history ?? null, error: null },
          }));
        }
      }
    })();
  }

  const customParts = selected ? (customByKey[selected] ?? []) : [];
  const selectable: (GrowthPart & { uid?: string })[] = bundle
    ? [...bundle.parts, ...bundle.optional, ...customParts]
    : [];
  const chosen = selected
    ? selectable.filter((p) => approved[partStateKey(selected, p)])
    : [];

  function addCustomStep() {
    if (!selected) return;
    const title = customTitle.trim();
    if (!title) return;
    const rawLines = customBody
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    const steps = rawLines.length > 0 ? rawLines : [title];
    const uid = `custom-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const part: CustomPart = {
      uid,
      id: "CUSTOM",
      name: title,
      title,
      why: "Added manually during review.",
      steps,
      evidence: [],
      core: false,
      confirmed_by_rule: false,
      custom: true,
      role: "supporting",
    };
    const sk = partStateKey(selected, part);
    setCustomByKey((prev) => ({ ...prev, [selected]: [...(prev[selected] ?? []), part] }));
    setApproved((prev) => ({ ...prev, [sk]: true }));
    setStepTexts((prev) => ({ ...prev, [sk]: steps.join("\n") }));
    setExpanded((prev) => ({ ...prev, [sk]: true }));
    setCustomTitle("");
    setCustomBody("");
    setAddingCustom(false);
  }

  function removeCustomPart(uid: string) {
    if (!selected) return;
    setCustomByKey((prev) => ({
      ...prev,
      [selected]: (prev[selected] ?? []).filter((p) => p.uid !== uid),
    }));
  }

  function addToPlan() {
    if (!bundle || !selected || chosen.length === 0) return;
    const draft = buildWorkbenchDraft(bundle, selected, chosen, selectable, approved, stepTexts);
    setMessage(null);
    setFeedback(null);
    start(async () => {
      const r = await confirmTaskAction(clientId, month, draft);
      if (r.ok) {
        onTaskChange(r.value);
        setFeedback("Added to this month's plan.");
      } else {
        setMessage(r.error);
      }
    });
  }

  function submitRejection(payload: { status: "rejected" | "dropped"; rejection_reason?: string; rejection_note?: string }) {
    if (!current || !payload.rejection_reason) return;
    const draft = bundle
      ? buildWorkbenchDraft(bundle, selected ?? current.key, chosen, selectable, approved, stepTexts)
      : null;
    const targetSearch = draft?.search ?? bundle?.keyword ?? bundle?.search ?? current.search;
    setMessage(null);
    setFeedback(null);
    start(async () => {
      const r = await rejectTaskAction(clientId, {
        month,
        kind: "growth_action",
        rule_id: draft?.rule_id ?? "GA",
        search: targetSearch,
        page: bundle?.page ?? current.page,
        title:
          draft?.title ??
          (targetSearch
            ? `Growth action: ${shortPage(current.page)} for “${targetSearch}”`
            : `Growth action: ${shortPage(current.page)}`),
        why: draft?.why ?? null,
        steps: draft?.steps ?? [],
        parts: draft?.parts ?? [],
        rejection_reason: payload.rejection_reason!,
        rejection_note: payload.rejection_note,
      });
      if (r.ok) {
        onTaskChange(r.value);
        setRejectOpen(false);
        const rec: PriorRejection = {
          id: r.value.id,
          month: r.value.month,
          search: r.value.search,
          rule_id: r.value.rule_id,
          title: r.value.title,
          rejection_reason: r.value.rejection_reason ?? payload.rejection_reason ?? null,
          rejection_reason_label:
            r.value.rejection_reason_label ??
            rejectionReasons.find((x) => x.key === payload.rejection_reason)?.label ??
            null,
          rejection_note: r.value.rejection_note ?? payload.rejection_note ?? null,
          rejected_by: r.value.rejected_by ?? null,
          rejected_at: r.value.rejected_at ?? new Date().toISOString(),
        };
        setSessionRejections((prev) => ({
          ...prev,
          [current.page]: [rec, ...(prev[current.page] ?? []).filter((x) => x.id !== rec.id)],
        }));
        setFeedback(`Rejected (${rec.rejection_reason_label ?? rec.rejection_reason}).`);
      } else {
        setMessage(r.error);
      }
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

  function taskCard(p: GrowthPart & { uid?: string }, held: boolean, c: WorkbenchItem) {
    if (!selected) return null;
    const sk = partStateKey(selected, p);
    const on = !held && Boolean(approved[sk]);
    const isEditing = Boolean(editingPart[sk]);
    const open = Boolean(expanded[sk]) || isEditing;
    const channels = CHANNEL[p.benefit ?? ""] ?? [];
    const currentText = stepTexts[sk] ?? p.steps.join("\n");
    const displaySteps = currentText
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    const edited = !p.custom && currentText.trim() !== p.steps.join("\n").trim();
    const isFq1 = p.id === "FQ-1";
    const isMc1 = p.id === "MC-1";

    return (
      <li
        key={sk}
        className="rounded-xl border px-[18px] py-3.5"
        style={
          held
            ? { borderStyle: "dashed", borderColor: TONE.miss.border, background: "#fcfafa" }
            : isFq1 && on
              ? { borderColor: "#00a99d", background: "#f7fcfb" }
              : { borderColor: on ? "#bfe9e4" : "#ececec", background: "#fff" }
        }
      >
        <div className="flex items-start gap-3">
          <button
            type="button"
            role="checkbox"
            aria-checked={on}
            aria-label={`Approve: ${p.title}`}
            disabled={held}
            onClick={() => setApproved((a) => ({ ...a, [sk]: !a[sk] }))}
            className="mt-0.5 flex h-5 w-5 shrink-0 cursor-pointer items-center justify-center rounded-[5px] border text-xs font-bold text-white disabled:cursor-not-allowed"
            style={on ? { background: TEAL, borderColor: TEAL } : { background: "#fff", borderColor: "#c5cdd2" }}
          >
            {on ? "✓" : ""}
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-[var(--font-heading)] text-[15px] font-bold text-[#0a0c0f]" style={held ? { color: "#7a838c" } : undefined}>
                {p.title}
              </span>
              {p.custom ? <Pill t="ok">Custom</Pill> : null}
              {edited ? <Pill t="warn">Edited</Pill> : null}
              {isMc1 ? <Pill t="lime">CTR · Title &amp; Meta</Pill> : null}
              {isFq1 ? <Pill t="ok">Site FAQ page</Pill> : null}
              {channels.map((ch) => (
                <Pill key={ch} t="ok">{ch}</Pill>
              ))}
              {p.role === "optional" ? <Pill t="info">Optional</Pill> : null}
              {held ? <Pill t="miss">Held: needs intent</Pill> : null}
            </div>
            {p.why ? <p className="mt-1 text-[13px] text-[#4a5560]">{p.why}</p> : null}

            {(isMc1 || isFq1) ? (
              <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
                {isMc1 ? (
                  <Link
                    href={`/${clientSlug}/ctr?page=${encodeURIComponent(c.page)}`}
                    className="font-semibold text-[#00857b] hover:underline"
                  >
                    Rewrite title &amp; meta in CTR Optimizer →
                  </Link>
                ) : null}
                {isFq1 ? (
                  <Link
                    href={`/${clientSlug}/inlinks?target=${encodeURIComponent(c.page)}`}
                    className="font-semibold text-[#00857b] hover:underline"
                  >
                    Open Inlink suggester →
                  </Link>
                ) : null}
              </div>
            ) : null}

            {open ? (
              <div className="mt-3 space-y-2.5 text-[13px]">
                {isEditing ? (
                  <div className="space-y-2">
                    <textarea
                      value={currentText}
                      onChange={(e) => setStepTexts((prev) => ({ ...prev, [sk]: e.target.value }))}
                      rows={Math.min(12, Math.max(3, displaySteps.length + 1))}
                      aria-label={`Steps for ${p.title}`}
                      className="w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-[13px] text-[#171a22] focus:border-[#00a99d] focus:outline-none"
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setEditingPart((prev) => ({ ...prev, [sk]: false }))}
                        className="cursor-pointer rounded-full bg-[#223540] px-3 py-1 text-xs font-semibold text-white"
                      >
                        Done editing
                      </button>
                      {!p.custom && edited ? (
                        <button
                          type="button"
                          onClick={() => setStepTexts((prev) => ({ ...prev, [sk]: p.steps.join("\n") }))}
                          className="cursor-pointer text-xs font-semibold text-[#7a838c] hover:text-[#0a0c0f]"
                        >
                          Reset steps
                        </button>
                      ) : null}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {displaySteps.map((step, idx) => (
                      <div key={`${sk}-s-${idx}`} className="flex items-start gap-2.5 text-[#171a22]">
                        <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-[#223540] text-[11px] font-bold text-white">
                          {idx + 1}
                        </span>
                        <span>{step}</span>
                      </div>
                    ))}
                  </div>
                )}

                {p.note && p.scope && p.scope !== "page-specific" ? (
                  <p className="rounded-[10px] border px-3 py-1.5 text-xs" style={toneStyle("warn")}>
                    {p.scope}: {p.note}
                  </p>
                ) : null}

                {p.evidence.length > 0 ? (
                  <button
                    type="button"
                    onClick={() => setTab("evidence")}
                    className="cursor-pointer text-xs font-semibold text-[#00857b] underline"
                  >
                    See the {p.evidence.length} signal{p.evidence.length === 1 ? "" : "s"} behind this →
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="flex shrink-0 flex-col items-end gap-1.5">
            <button
              type="button"
              onClick={() => setExpanded((e) => ({ ...e, [sk]: !e[sk] }))}
              className="cursor-pointer text-xs font-semibold text-[#7a838c] hover:text-[#0a0c0f]"
            >
              {displaySteps.length} step{displaySteps.length === 1 ? "" : "s"} {open ? "−" : "+"}
            </button>
            {!held ? (
              <button
                type="button"
                onClick={() => {
                  setExpanded((e) => ({ ...e, [sk]: true }));
                  setEditingPart((prev) => ({ ...prev, [sk]: !prev[sk] }));
                }}
                className="cursor-pointer text-xs font-semibold text-[#00857b] hover:underline"
              >
                {isEditing ? "Close editor" : "Edit steps"}
              </button>
            ) : null}
            {p.custom && p.uid ? (
              <button
                type="button"
                onClick={() => removeCustomPart(p.uid!)}
                className="cursor-pointer text-xs font-semibold text-[oklch(0.48_0.17_25)] hover:underline"
              >
                Remove
              </button>
            ) : null}
          </div>
        </div>
      </li>
    );
  }

  function itemMetricsLine(item: WorkbenchItem): ReactNode {
    if (item.candidate) {
      const c = item.candidate;
      return (
        <span>
          #{num(c.position, 1)} → <strong style={{ color: "#00857b" }}>#{c.target_position}</strong> · +
          {num(c.expected_extra_clicks, 1)} clicks / 3 mo · {num(c.impressions)} impressions
        </span>
      );
    }
    if (item.trafficRow) {
      const p = item.trafficRow;
      return (
        <span>
          Last month: {num(p.sessions.current)} ({fmtPct(p.sessions.change_pct)}) · 3 mo: {num(p.three_months.current)} ({fmtPct(p.three_months.change_pct)}) · -{num(p.lost_month)} lost/mo
        </span>
      );
    }
    if (item.leadRow) {
      const l = item.leadRow;
      const nounPlural = leads?.noun.plural ?? "conversions";
      return (
        <span>
          {num(l.sessions)} sessions · {num(l.conversions)} {nounPlural} ({l.conversion_rate.toFixed(1)}%) · +{num(l.missed_conversions, 1)} missed
        </span>
      );
    }
    return null;
  }

  function diagnosed(c: WorkbenchItem, b: OkBundle) {
    const selKey = c.key;
    const ctx = b.context;
    const v = verdictOf(b, customParts.length);
    const held = b.held ?? [];
    const unverified = ctx?.evidence.unverified ?? [];
    const checklist = b.checklist ?? ctx?.checklist ?? [];
    const neededChecklist = checklist.filter((item) => item.status === "needed").length;
    const effectiveFocus: EngineKind = b.focus ?? ctx?.focus ?? activeFocus;
    const effectiveStyleNotes = styleNotes ?? ctx?.style_notes;

    const mergedPriorRejections: PriorRejection[] = [
      ...(sessionRejections[c.page] ?? []),
      ...(b.prior_rejections ?? []).filter(
        (pr) =>
          !nonRejectedTaskIds.has(pr.id) &&
          !(sessionRejections[c.page] ?? []).some((sr) => sr.id === pr.id),
      ),
    ];

    const defaultSerpQuery = (b.search || c.search).trim().toLowerCase();
    const activeSerpQuery = serpQueryBySel[selKey] ?? defaultSerpQuery;
    const serpEntry = serpBySearch[activeSerpQuery];
    const serpQuestions = serpEntry?.data?.questions ?? [];
    const fq1Part = [...b.parts, ...b.optional].find((p) => p.id === "FQ-1");

    const histEntry = historyByPage[b.page];
    const effectiveHistory = histEntry?.data ?? b.page_history ?? null;
    const historyCount =
      (effectiveHistory?.crawl_changes.length ?? 0) +
      (effectiveHistory?.tasks.length ?? 0) +
      (effectiveHistory?.annotations.length ?? 0);

    const other =
      b.suggested_page ??
      (b.better_page
        ? {
            url: b.better_page.url,
            why: b.better_page.why,
            next: "Review that page on its own. This action is not moved to it.",
            exists: true,
            kind: null,
            title: null,
          }
        : null);
    const otherRow = other?.url
      ? items.find((x) => x.page === other.url && x.search === c.search) ??
        items.find((x) => x.page === other.url)
      : undefined;
    const already = inPlan(c.page);

    const tabs: { key: Tab; label: string; badge: ReactNode }[] = [
      {
        key: "tasks",
        label: "Recommended tasks",
        badge: selectable.length ? <Pill t="ok">{chosen.length}/{selectable.length}</Pill> : null,
      },
      {
        key: "checklist",
        label: "Page checklist",
        badge:
          checklist.length > 0 ? (
            <Pill t={neededChecklist > 0 ? "miss" : "ok"}>
              {neededChecklist > 0 ? `${neededChecklist} needed` : "Ready"}
            </Pill>
          ) : null,
      },
      {
        key: "evidence",
        label: "Evidence",
        badge: unverified.length ? <Pill t="warn">{unverified.length} unverified</Pill> : null,
      },
      {
        key: "serp",
        label: "Results page",
        badge: ctx && !ctx.intent.read ? <Pill t="miss">Not read</Pill> : null,
      },
      {
        key: "history",
        label: "History",
        badge:
          mergedPriorRejections.length > 0 ? (
            <Pill t="miss">{mergedPriorRejections.length} rejected</Pill>
          ) : historyCount > 0 ? (
            <Pill t="info">{historyCount}</Pill>
          ) : null,
      },
      {
        key: "other",
        label: "Other pages",
        badge: other ? <Pill t="info">1</Pill> : null,
      },
    ];

    return (
      <>
        <div className="border-b border-[#e8e8e8] bg-white px-7 pt-[18px]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                  Diagnosis
                </span>
                <Pill t="ok">Focus: {FOCUS_LABEL[effectiveFocus]}</Pill>
              </div>
              <h2 className="mt-1 font-[var(--font-heading)] text-[22px] font-bold text-[#0a0c0f]">
                “{c.search || b.keyword}”
              </h2>
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-[#4a5560]">
                <span
                  className="inline-flex items-center gap-1 rounded-full px-2.5 py-[3px] font-semibold text-white"
                  style={{ background: DARK }}
                  title="This diagnosis and its tasks stay on this page"
                >
                  <LockIcon />
                  {shortPage(c.page)}
                </span>
                {itemMetricsLine(c)}
              </div>
            </div>

            <div className="flex flex-none flex-wrap items-center gap-2">
              {!already ? (
                <button
                  type="button"
                  onClick={() => setRejectOpen((o) => !o)}
                  disabled={pending}
                  className="cursor-pointer rounded-full border border-[oklch(0.88_0.06_25)] bg-white px-4 py-2 text-[13px] font-semibold text-[oklch(0.48_0.17_25)] hover:bg-[oklch(0.965_0.025_25)] disabled:opacity-50"
                >
                  {rejectOpen ? "Cancel reject" : "Reject"}
                </button>
              ) : null}

              {v.level === "none" ? null : already ? (
                <span
                  className="rounded-full px-[18px] py-2 text-[13px] font-semibold"
                  style={{ background: "#e6f7f5", color: "#00665f" }}
                >
                  In the {monthName} plan ✓
                </span>
              ) : (
                <button
                  type="button"
                  onClick={addToPlan}
                  disabled={pending || chosen.length === 0 || full}
                  className="cursor-pointer rounded-full px-[18px] py-2 text-[13px] font-semibold text-white disabled:cursor-not-allowed"
                  style={{ background: pending || chosen.length === 0 || full ? "#c5cdd2" : DARK }}
                >
                  {pending ? (
                    <>
                      <Spinner />
                      Adding…
                    </>
                  ) : full ? (
                    "Plan is full"
                  ) : (
                    `Add ${chosen.length} task${chosen.length === 1 ? "" : "s"} to plan`
                  )}
                </button>
              )}
            </div>
          </div>

          <div className="mt-3 rounded-xl border px-4 py-3 text-[13px]" style={toneStyle(v.t)}>
            <span className="mr-2 rounded-full bg-white px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide">
              {v.label}
            </span>
            <strong>{v.title}</strong>
            {v.story ? <span className="mt-1 block">{v.story}</span> : null}
          </div>

          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {chipsOf(b, c).map((chip) => (
              <span
                key={chip.label}
                title={chip.sub}
                className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1 text-xs"
                style={toneStyle(chip.t)}
              >
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: TONE[chip.t].dot }} />
                <span className="text-[#7a838c]">{chip.label}</span>
                <strong>{chip.value}</strong>
              </span>
            ))}
          </div>

          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1" role="tablist">
            {tabs.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => {
                  setTab(t.key);
                  if (t.key === "serp" && !serpEntry?.data && !serpEntry?.loading) {
                    loadSerp(activeSerpQuery, false);
                  }
                  if (t.key === "history" && !effectiveHistory && !histEntry?.loading) {
                    loadPageHistory(b.page);
                  }
                }}
                className="flex cursor-pointer items-center gap-1.5 border-b-2 pb-2.5 text-[13px] font-semibold transition-colors"
                style={
                  tab === t.key
                    ? { color: "#0a0c0f", borderColor: DARK }
                    : { color: "#7a838c", borderColor: "transparent" }
                }
              >
                {t.label}
                {t.badge}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-3.5 px-7 pb-8 pt-4.5 text-sm">
          {message ? (
            <p role="alert" className="rounded-xl border px-4 py-2.5 text-[13px]" style={toneStyle("miss")}>
              {message}
            </p>
          ) : null}
          {feedback ? (
            <p role="status" className="rounded-xl border px-4 py-2.5 text-[13px]" style={toneStyle("ok")}>
              {feedback}
            </p>
          ) : null}

          {rejectOpen ? (
            <RejectForm
              reasons={rejectionReasons}
              busy={pending}
              onSubmit={submitRejection}
              onCancel={() => setRejectOpen(false)}
            />
          ) : null}

          <PriorRejectionsCard rejections={mergedPriorRejections} />

          <StyleNotesBanner styleNotes={effectiveStyleNotes} clientSlug={clientSlug} compact />

          {tab === "tasks" ? (
            <>
              {b.focus_order_reason ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#ececec] bg-white px-4 py-2.5 text-xs text-[#4a5560]">
                  <span>
                    <strong className="text-[#0a0c0f]">Ordered for {FOCUS_LABEL[effectiveFocus]}:</strong>{" "}
                    {b.focus_order_reason}
                  </span>
                </div>
              ) : null}

              {checklist.length > 0 ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#ececec] bg-white px-4 py-2.5 text-xs">
                  <span className="text-[#4a5560]">
                    <strong className="text-[#0a0c0f]">{ctx?.page_type.name ?? "Page"} checklist:</strong>{" "}
                    {neededChecklist > 0
                      ? `${neededChecklist} needed before publishing`
                      : "All automated checks look covered"}
                  </span>
                  <button
                    type="button"
                    onClick={() => setTab("checklist")}
                    className="cursor-pointer font-semibold text-[#00857b] hover:underline"
                  >
                    View {checklist.length} checklist items →
                  </button>
                </div>
              ) : null}

              {held.length > 0 ? (
                <div
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dashed px-4 py-3 text-[13px]"
                  style={toneStyle("miss")}
                >
                  <span>
                    <strong>Intent not read.</strong> {held.length} task{held.length === 1 ? " is" : "s are"} held until the results page is read.
                  </span>
                  <button
                    type="button"
                    onClick={() => diagnose(c)}
                    disabled={diag?.loading}
                    className="cursor-pointer rounded-full border bg-white px-3.5 py-1 text-xs font-semibold"
                    style={{ borderColor: TONE.miss.border }}
                  >
                    {diag?.loading ? "Reading…" : "Read it now"}
                  </button>
                </div>
              ) : null}

              {v.level === "none" ? (
                <p className="rounded-xl border border-[#ececec] bg-white px-4 py-3 text-[13px] text-[#4a5560]">
                  Nothing is recommended on this page for this search.
                  {other ? " See Other pages for the page that suits it." : ""} You can still add a custom step below.
                </p>
              ) : null}

              <ul className="space-y-2.5">
                {b.parts.map((p) => taskCard(p, false, c))}
                {b.optional.map((p) => taskCard(p, false, c))}
                {customParts.map((p) => taskCard(p, false, c))}
                {held.map((p) => taskCard(p, true, c))}
              </ul>

              {/* Add custom step */}
              {!already ? (
                addingCustom ? (
                  <div className="rounded-xl border border-[#ececec] bg-white p-4">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                        Add a custom step
                      </span>
                      <button
                        type="button"
                        onClick={() => setAddingCustom(false)}
                        className="cursor-pointer text-xs font-semibold text-[#7a838c] hover:text-[#0a0c0f]"
                      >
                        Cancel
                      </button>
                    </div>
                    <div className="mt-2.5 space-y-2.5">
                      <input
                        type="text"
                        value={customTitle}
                        onChange={(e) => setCustomTitle(e.target.value)}
                        placeholder="Step title (e.g. Add case study metrics above the CTA)"
                        aria-label="Custom step title"
                        className="w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-[13px] text-[#171a22] placeholder:text-[#7a838c] focus:border-[#00a99d] focus:outline-none"
                      />
                      <textarea
                        value={customBody}
                        onChange={(e) => setCustomBody(e.target.value)}
                        rows={3}
                        placeholder="Step instructions (one per line, optional)"
                        aria-label="Custom step instructions"
                        className="w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-[13px] text-[#171a22] placeholder:text-[#7a838c] focus:border-[#00a99d] focus:outline-none"
                      />
                      <button
                        type="button"
                        disabled={!customTitle.trim()}
                        onClick={addCustomStep}
                        className="cursor-pointer rounded-full bg-[#223540] px-4 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45"
                      >
                        Add custom step
                      </button>
                    </div>
                  </div>
                ) : (
                  <div>
                    <button
                      type="button"
                      onClick={() => setAddingCustom(true)}
                      className="cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-4 py-1.5 text-xs font-semibold text-[#223540] hover:bg-[#eef8f7]"
                    >
                      + Add custom step
                    </button>
                  </div>
                )
              ) : null}
            </>
          ) : null}

          {tab === "checklist" ? (
            <ChecklistTab
              items={checklist}
              pageTypeName={ctx?.page_type.name}
              pageTypeKey={ctx?.page_type.type}
              focus={effectiveFocus}
            />
          ) : null}

          {tab === "evidence" ? (
            <>
              <FaqEvidenceCard
                questions={ctx?.winners?.comparison?.questions}
                serpQuestions={serpQuestions}
                fq1Part={fq1Part}
                clientSlug={clientSlug}
                pageUrl={c.page}
              />
              {unverified.length > 0 ? (
                <div className="rounded-xl border bg-white px-[18px] py-4" style={{ borderColor: TONE.warn.border }}>
                  <div className="text-[11px] font-bold uppercase tracking-[0.12em]" style={{ color: TONE.warn.fg }}>
                    Not verified
                  </div>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px] text-[#4a5560]">
                    {unverified.map((u) => (
                      <li key={u}>{u}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {[...b.parts, ...b.optional, ...held]
                .filter((p) => p.evidence.length > 0)
                .map((p) => (
                  <div key={p.id} className="rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
                    <h3 className="font-[var(--font-heading)] text-[14px] font-bold text-[#0a0c0f]">
                      Behind “{p.title}”
                    </h3>
                    <ul className="mt-2 space-y-1.5 text-[13px] text-[#4a5560]">
                      {p.evidence.map((e) => (
                        <li key={e} className="border-l-2 border-[#e3e6e8] pl-2.5">
                          {e}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              {ctx?.winners?.llm.ok ? (
                <div className="rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
                  <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                    In AI answers
                  </div>
                  <p className="mt-1.5 text-[13px] text-[#4a5560]">
                    Asked “{ctx.winners.llm.prompt}” on {formatDay(ctx.winners.llm.run_date)}.
                  </p>
                  <ul className="mt-2 space-y-1.5 text-[13px] text-[#4a5560]">
                    {(ctx.winners.llm.platforms ?? []).map((p) => (
                      <li key={p.platform} className="border-l-2 border-[#e3e6e8] pl-2.5">
                        <strong className="text-[#0a0c0f]">{p.platform}:</strong>{" "}
                        {p.brand_mentioned ? `named${p.brand_rank ? ` (${p.brand_rank} of ${p.total_brands})` : ""}` : "not named"},{" "}
                        {p.client_cited ? "cited" : "not cited"}
                        {p.brands.length ? `. Named first: ${p.brands.slice(0, 3).join(", ")}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {b.left_out.length > 0 ? (
                <div className="rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
                  <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                    Considered but not included
                  </div>
                  <ul className="mt-2 space-y-1.5 text-[13px] text-[#4a5560]">
                    {b.left_out.map((l) => (
                      <li key={l.id}>
                        <strong className="text-[#0a0c0f]">{l.name}.</strong> {l.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          ) : null}

          {tab === "serp" ? (
            <SerpTab
              defaultSearch={defaultSerpQuery}
              activeSearch={activeSerpQuery}
              serp={serpEntry?.data ?? null}
              loading={Boolean(serpEntry?.loading)}
              pulling={Boolean(serpEntry?.pulling)}
              error={serpEntry?.error ?? null}
              intent={ctx?.intent}
              onLookup={(q) => {
                setSerpQueryBySel((prev) => ({ ...prev, [selKey]: q.trim().toLowerCase() }));
                loadSerp(q, false);
              }}
              onPull={(q) => {
                setSerpQueryBySel((prev) => ({ ...prev, [selKey]: q.trim().toLowerCase() }));
                loadSerp(q, true);
              }}
            />
          ) : null}

          {tab === "history" ? (
            <HistoryTab
              history={effectiveHistory}
              loading={Boolean(histEntry?.loading)}
              error={histEntry?.error ?? null}
              onRefresh={() => loadPageHistory(b.page)}
            />
          ) : null}

          {tab === "other" ? (
            other ? (
              <>
                <div className="rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
                  {other.url ? (
                    <div className="break-all font-[var(--font-heading)] text-[15px] font-bold text-[#0a0c0f]">
                      {shortPage(other.url)}
                    </div>
                  ) : (
                    <div className="font-[var(--font-heading)] text-[15px] font-bold text-[#0a0c0f]">
                      No page of the right kind on this site
                    </div>
                  )}
                  <p className="mt-1 text-[13px] text-[#4a5560]">{other.why}</p>
                  {otherRow ? (
                    <button
                      type="button"
                      onClick={() => select(otherRow.key)}
                      className="mt-3 cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-3.5 py-1 text-xs font-semibold text-[#223540] hover:bg-[#eef8f7]"
                    >
                      Open in the list
                    </button>
                  ) : other.url ? (
                    <p className="mt-2 text-xs text-[#7a838c]">
                      That page is not among this list&apos;s opportunities, so it has no row to open.
                    </p>
                  ) : null}
                </div>
                <p className="text-xs text-[#7a838c]">
                  Suggestions only. This diagnosis and its tasks stay on {shortPage(c.page)}.
                </p>
              </>
            ) : (
              <div className="rounded-xl border border-dashed border-[#d3d7d9] bg-white px-4 py-4 text-[13px] text-[#7a838c]">
                No other page of this site suits this search better. This diagnosis stays on {shortPage(c.page)}.
              </div>
            )
          ) : null}
        </div>
      </>
    );
  }

  const listCountLabel =
    activeFocus === "visibility"
      ? `${num(data?.counts.found ?? 0)} in reach`
      : activeFocus === "traffic"
        ? `${num(traffic?.dropped_pages.length ?? 0)} dropped`
        : `${num(leads?.candidates.length ?? 0)} lagging`;

  function fallbackDiagnosed(item: WorkbenchItem, fb: Diagnosis) {
    const checklist = fb.context?.checklist ?? [];
    const neededChecklist = checklist.filter((x) => x.status === "needed").length;
    const effectiveFocus: EngineKind = fb.focus ?? activeFocus;
    const effectiveStyleNotes = styleNotes ?? fb.context?.style_notes;
    const histEntry = historyByPage[fb.page];
    const effectiveHistory = histEntry?.data ?? fb.page_history ?? null;
    const historyCount =
      (effectiveHistory?.crawl_changes.length ?? 0) +
      (effectiveHistory?.tasks.length ?? 0) +
      (effectiveHistory?.annotations.length ?? 0);
    const mergedPriorRejections = sessionRejections[item.page] ?? [];
    const already = inPlan(item.page);

    const fbParts: (GrowthPart & { uid?: string })[] = [
      ...fb.prescriptions.map((p) => ({
        id: p.action_id,
        name: p.title,
        title: p.title,
        why: p.why,
        steps: p.steps,
        evidence: p.evidence,
        core: true,
        confirmed_by_rule: true,
        role: "primary" as const,
      })),
      ...fb.suggestions.map((s) => ({
        id: s.id,
        name: s.title,
        title: s.title,
        why: s.why,
        steps: s.steps,
        evidence: s.evidence,
        core: true,
        confirmed_by_rule: false,
        role: "supporting" as const,
        needs_to_confirm: s.needs_to_confirm,
      })),
      ...customParts,
    ];
    const fbChosen = fbParts.filter((p) => approved[partStateKey(item.key, p)]);

    function addPageDiagToPlan() {
      if (fbChosen.length === 0) return;
      const steps: string[] = [];
      fbChosen.forEach((p, i) => {
        const sk = partStateKey(item.key, p);
        const raw = stepTexts[sk] ?? p.steps.join("\n");
        steps.push(`# ${i + 1}. ${p.name}`);
        steps.push(
          ...raw
            .split("\n")
            .map((l) => l.trim())
            .filter(Boolean),
        );
      });
      const focusWord = FOCUS_LABEL[effectiveFocus];
      const draft: TaskDraft = {
        kind: "growth_action",
        rule_id: fbChosen[0]?.id ?? "PD",
        search: "",
        page: item.page,
        title: `${focusWord}: ${shortPage(item.page)}`,
        why: fbChosen.map((p) => p.why).filter(Boolean).join(" ") || `${focusWord} diagnosis for ${shortPage(item.page)}.`,
        steps,
        done_when: "Every selected step above is live on the page.",
        metric: effectiveFocus === "traffic" ? "Organic sessions in GA4" : "Organic conversions and engagement in GA4",
        effort_min: null,
        evidence: fbChosen.flatMap((p) => p.evidence),
        parts: fbChosen.map((p) => ({
          id: p.custom ? "CUSTOM" : p.id,
          name: p.name,
          ...(p.custom ? { custom: true } : {}),
        })),
      };
      setMessage(null);
      setFeedback(null);
      start(async () => {
        const r = await confirmTaskAction(clientId, month, draft);
        if (r.ok) {
          onTaskChange(r.value);
          setFeedback("Added to this month's plan.");
        } else {
          setMessage(r.error);
        }
      });
    }

    return (
      <>
        <div className="border-b border-[#e8e8e8] bg-white px-7 pt-[18px]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                  {FOCUS_LABEL[effectiveFocus]} diagnosis
                </span>
                <Pill t="ok">Focus: {FOCUS_LABEL[effectiveFocus]}</Pill>
                {fb.context?.page_type?.name ? <Pill t="info">{fb.context.page_type.name}</Pill> : null}
              </div>
              <h2 className="mt-1 font-[var(--font-heading)] text-[22px] font-bold text-[#0a0c0f]">
                {shortPage(item.page)}
              </h2>
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-[#4a5560]">
                <span
                  className="inline-flex items-center gap-1 rounded-full px-2.5 py-[3px] font-semibold text-white"
                  style={{ background: DARK }}
                  title="This diagnosis and its tasks stay on this page"
                >
                  <LockIcon />
                  {shortPage(item.page)}
                </span>
                {itemMetricsLine(item)}
              </div>
            </div>
            <div className="flex flex-none flex-wrap items-center gap-2">
              {!already ? (
                <button
                  type="button"
                  onClick={() => setRejectOpen((o) => !o)}
                  disabled={pending}
                  className="cursor-pointer rounded-full border border-[oklch(0.88_0.06_25)] bg-white px-4 py-2 text-[13px] font-semibold text-[oklch(0.48_0.17_25)] hover:bg-[oklch(0.965_0.025_25)] disabled:opacity-50"
                >
                  {rejectOpen ? "Cancel reject" : "Reject"}
                </button>
              ) : null}

              {already ? (
                <span
                  className="rounded-full px-[18px] py-2 text-[13px] font-semibold"
                  style={{ background: "#e6f7f5", color: "#00665f" }}
                >
                  In the {monthName} plan ✓
                </span>
              ) : (
                <button
                  type="button"
                  onClick={addPageDiagToPlan}
                  disabled={pending || fbChosen.length === 0 || full}
                  className="cursor-pointer rounded-full px-[18px] py-2 text-[13px] font-semibold text-white disabled:cursor-not-allowed"
                  style={{ background: pending || fbChosen.length === 0 || full ? "#c5cdd2" : DARK }}
                >
                  {pending
                    ? "Adding…"
                    : full
                      ? `${monthName} plan is full`
                      : `Add ${fbChosen.length} task${fbChosen.length === 1 ? "" : "s"} to plan`}
                </button>
              )}

              <button
                type="button"
                onClick={() => diagnose(item)}
                className="cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-3.5 py-2 text-[13px] font-semibold text-[#223540] hover:bg-[#eef8f7]"
              >
                Re-read
              </button>
            </div>
          </div>

          <div className="mt-3.5 flex flex-wrap gap-1 border-t border-[#f1f2f3]">
            {[
              {
                key: "tasks" as Tab,
                label: "Recommended tasks",
                badge: fbParts.length ? <Pill t="ok">{fbChosen.length}/{fbParts.length}</Pill> : null,
              },
              {
                key: "checklist" as Tab,
                label: "Page checklist",
                badge: checklist.length > 0 ? <Pill t={neededChecklist > 0 ? "miss" : "ok"}>{neededChecklist > 0 ? `${neededChecklist} needed` : "Ready"}</Pill> : null,
              },
              { key: "history" as Tab, label: "History", badge: historyCount > 0 ? <Pill t="info">{historyCount}</Pill> : null },
            ].map((t) => {
              const active = tab === t.key;
              return (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => {
                    setTab(t.key);
                    if (t.key === "history" && !histEntry) loadPageHistory(fb.page);
                  }}
                  className="inline-flex cursor-pointer items-center gap-1.5 border-b-2 px-3 py-2.5 text-[13px] font-semibold transition-colors"
                  style={
                    active
                      ? { borderColor: TEAL, color: "#00857b" }
                      : { borderColor: "transparent", color: "#4a5560" }
                  }
                >
                  {t.label}
                  {t.badge}
                </button>
              );
            })}
          </div>
        </div>

        <div className="space-y-4 px-7 py-5">
          {message ? (
            <p role="alert" className="rounded-xl border px-4 py-3 text-[13px]" style={toneStyle("miss")}>
              {message}
            </p>
          ) : null}
          {feedback ? (
            <p className="rounded-xl border px-4 py-3 text-[13px]" style={toneStyle("ok")}>
              {feedback}
            </p>
          ) : null}

          {rejectOpen ? (
            <RejectForm
              reasons={rejectionReasons}
              busy={pending}
              onSubmit={submitRejection}
              onCancel={() => setRejectOpen(false)}
            />
          ) : null}

          {mergedPriorRejections.length > 0 ? <PriorRejectionsCard rejections={mergedPriorRejections} /> : null}

          {tab === "tasks" ? (
            <>
              <StyleNotesBanner styleNotes={effectiveStyleNotes} clientSlug={clientSlug} compact />

              {fb.focus_order_reason ? (
                <div className="rounded-xl border border-[#ececec] bg-white px-4 py-2.5 text-xs text-[#4a5560]">
                  <strong className="text-[#0a0c0f]">Ordered for {FOCUS_LABEL[effectiveFocus]}:</strong> {fb.focus_order_reason}
                </div>
              ) : null}

              {checklist.length > 0 ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#ececec] bg-white px-4 py-2.5 text-xs">
                  <span className="text-[#4a5560]">
                    <strong className="text-[#0a0c0f]">{fb.context?.page_type?.name ?? "Page"} checklist:</strong>{" "}
                    {neededChecklist > 0
                      ? `${neededChecklist} needed before publishing`
                      : "All checks clear"}
                  </span>
                  <button
                    type="button"
                    onClick={() => setTab("checklist")}
                    className="cursor-pointer font-semibold text-[#00857b] hover:underline"
                  >
                    View {checklist.length} checklist items →
                  </button>
                </div>
              ) : null}

              {fb.observations.length > 0 ? (
                <div className="rounded-xl border border-[#ececec] bg-white p-4">
                  <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">What the page shows</div>
                  <ul className="mt-2.5 space-y-2 text-[13px]">
                    {fb.observations.map((o, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <Pill t={o.level === "problem" ? "miss" : o.level === "ok" ? "ok" : "info"}>
                          {o.level === "problem" ? "Issue" : o.level === "ok" ? "OK" : "Note"}
                        </Pill>
                        <span className="text-[#171a22]">{o.text}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {fbParts.length > 0 ? (
                <ul className="space-y-2.5">{fbParts.map((p) => taskCard(p, false, item))}</ul>
              ) : (
                <div className="rounded-xl border border-dashed border-[#d3d7d9] bg-white px-4 py-4 text-[13px] text-[#7a838c]">
                  No specific issues were flagged from this read. You can still add a custom step below.
                </div>
              )}

              {addingCustom ? (
                <div className="space-y-3 rounded-xl border border-[#bfe9e4] bg-white p-4">
                  <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#00665f]">
                    Add a custom step
                  </div>
                  <input
                    type="text"
                    value={customTitle}
                    onChange={(e) => setCustomTitle(e.target.value)}
                    placeholder="Step title"
                    className="w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-[13px] text-[#171a22] placeholder:text-[#7a838c] focus:border-[#00a99d] focus:outline-none"
                  />
                  <textarea
                    value={customBody}
                    onChange={(e) => setCustomBody(e.target.value)}
                    rows={3}
                    placeholder="Instructions (one step per line)"
                    className="w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-[13px] text-[#171a22] placeholder:text-[#7a838c] focus:border-[#00a99d] focus:outline-none"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={addCustomStep}
                      disabled={!customTitle.trim()}
                      className="cursor-pointer rounded-full bg-[#223540] px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      Add step to plan
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setAddingCustom(false);
                        setCustomTitle("");
                        setCustomBody("");
                      }}
                      className="cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-4 py-1.5 text-xs font-semibold text-[#4a5560]"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <button
                    type="button"
                    onClick={() => setAddingCustom(true)}
                    className="cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-4 py-1.5 text-xs font-semibold text-[#223540] hover:border-[#00a99d] hover:bg-[#e6f7f5]"
                  >
                    + Add custom step
                  </button>
                </div>
              )}
            </>
          ) : null}

          {tab === "checklist" ? (
            <ChecklistTab
              items={checklist}
              pageTypeName={fb.context?.page_type?.name}
              pageTypeKey={fb.context?.page_type?.type}
              focus={effectiveFocus}
            />
          ) : null}

          {tab === "history" ? (
            <HistoryTab
              history={effectiveHistory}
              loading={Boolean(histEntry?.loading)}
              error={histEntry?.error ?? null}
              onRefresh={() => loadPageHistory(fb.page)}
            />
          ) : null}
        </div>
      </>
    );
  }

  return (
    <div className="flex min-h-[36rem] flex-col overflow-hidden rounded-xl border border-[#e8e8e8] bg-[#f6f7f7] text-sm lg:h-[calc(100vh-14rem)]">
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="flex w-full flex-none flex-col border-b border-[#e8e8e8] bg-white lg:w-[370px] lg:border-b-0 lg:border-r xl:w-[440px]">
          <div className="flex flex-col gap-2.5 border-b border-[#eef0f1] px-4 py-3">
            <div className="flex items-baseline justify-between gap-2">
              <div className="flex items-center gap-2">
                <h2 className="font-[var(--font-heading)] text-base font-bold text-[#0a0c0f]">Opportunities</h2>
                <Pill t="ok">{FOCUS_LABEL[activeFocus]}</Pill>
              </div>
              <span className="text-xs text-[#7a838c] tabular-nums">{listCountLabel}</span>
            </div>

            <div className="flex items-center gap-2 rounded-[10px] border border-[#e3e6e8] bg-white px-3">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#7a838c" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
                <circle cx="11" cy="11" r="7" />
                <path d="m20 20-3.5-3.5" />
              </svg>
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={activeFocus === "visibility" ? "Find a search or page" : "Find a page"}
                aria-label={activeFocus === "visibility" ? "Find a search or page" : "Find a page"}
                className="flex-1 bg-transparent py-2 text-[13px] text-[#171a22] placeholder:text-[#7a838c] focus:outline-none"
              />
            </div>

            <div className="flex flex-wrap gap-1.5">
              {activeTiers.map((t) => {
                const count = t.key === null ? tierCounts.all : (tierCounts[t.key] ?? 0);
                const active = tier === t.key;
                return (
                  <button
                    key={t.label}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setTier(t.key)}
                    className="cursor-pointer rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors"
                    style={
                      active
                        ? { background: DARK, color: "#fff", borderColor: DARK }
                        : { background: "#fff", borderColor: "#e3e6e8", color: "#4a5560" }
                    }
                  >
                    {t.label} <span className="font-medium opacity-65">{count}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <ul className="max-h-[22rem] flex-1 overflow-y-auto lg:max-h-none">
            {rows.map((c) => {
              const key = c.key;
              const d = diags[key];
              const state = inPlan(c.page) ? TEAL : d?.bundle || d?.fallback ? DARK : "#d3d7d9";
              const flags = flagsFor(c, d);
              const isSelected = selected === key;
              return (
                <li key={key}>
                  <button
                    type="button"
                    onClick={() => select(key)}
                    aria-current={isSelected ? "true" : undefined}
                    className={`block w-full cursor-pointer border-b border-[#f1f2f3] px-4 py-3 text-left transition-colors ${
                      isSelected ? "bg-[#eef8f7]" : "bg-white hover:bg-[#f8f8f8]"
                    }`}
                    style={isSelected ? { boxShadow: `inset 3px 0 0 ${TEAL}` } : undefined}
                  >
                    <div className="flex items-start gap-2.5">
                      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: state }} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="truncate text-[13px] font-semibold text-[#0a0c0f]">{c.title}</span>
                          <span className="shrink-0 font-[var(--font-heading)] text-sm font-bold text-[#0a0c0f] tabular-nums">
                            {c.rightMetric}
                          </span>
                        </div>
                        <div className="mt-0.5 flex items-baseline justify-between gap-2 text-[11px] text-[#7a838c]">
                          <span className="truncate">{c.subtitle}</span>
                          <span className="shrink-0 tabular-nums">{c.rightSubMetric}</span>
                        </div>
                        {flags.length > 0 ? (
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {flags.map((f) => (
                              <Pill key={f.text} t={f.t}>
                                {f.text}
                              </Pill>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </button>
                </li>
              );
            })}
            {rows.length === 0 ? (
              <li className="px-4 py-6 text-center text-[13px] text-[#7a838c]">
                No opportunities match this filter.
              </li>
            ) : null}
          </ul>

          <div className="flex flex-wrap gap-3 border-t border-[#f1f2f3] px-4 py-2 text-xs text-[#7a838c]">
            {[
              ["#d3d7d9", "Not reviewed"],
              [DARK, "Diagnosed"],
              [TEAL, "In plan"],
            ].map(([color, label]) => (
              <span key={label} className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ background: color }} />
                {label}
              </span>
            ))}
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex-1 overflow-y-auto bg-[#f6f7f7]">
            {!current ? (
              <div className="flex h-full min-h-[18rem] flex-col items-center justify-center px-8 text-center">
                <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                  Decision engine workbench
                </span>
                <h2 className="mt-1.5 font-[var(--font-heading)] text-xl font-bold text-[#0a0c0f]">
                  {activeFocus === "visibility" ? "Pick a search to diagnose" : "Pick a page to diagnose"}
                </h2>
                <p className="mt-2 max-w-md text-[13px] text-[#4a5560]">
                  {activeFocus === "visibility"
                    ? "The engine reads the page live, checks the results page, runs the page-type checklist, and orders recommended tasks for your "
                    : activeFocus === "traffic"
                      ? "The engine reads the page live, checks which searches lost clicks, runs the page-type checklist, and orders recovery tasks for your "
                      : "The engine reads the page live, checks conversion paths and CTAs, runs the page-type checklist, and orders conversion tasks for your "}
                  <strong className="text-[#0a0c0f]">{FOCUS_LABEL[activeFocus]}</strong> focus.
                </p>
              </div>
            ) : diag?.loading && !bundle && !fallbackDiag ? (
              <div className="flex h-full min-h-[18rem] flex-col items-center justify-center gap-3 text-[13px] text-[#4a5560]">
                <span
                  className="h-[30px] w-[30px] animate-spin rounded-full border-[3px] border-[#e3e6e8]"
                  style={{ borderTopColor: TEAL }}
                />
                {LOADING_COPY[activeFocus]}
              </div>
            ) : bundle ? (
              diagnosed(current, bundle)
            ) : fallbackDiag ? (
              fallbackDiagnosed(current, fallbackDiag)
            ) : (
              <div className="space-y-4 px-7 py-6">
                <div className="rounded-xl border border-[#ececec] bg-white p-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                      Selected opportunity
                    </span>
                    <Pill t="ok">Focus: {FOCUS_LABEL[activeFocus]}</Pill>
                  </div>
                  <h2 className="mt-1 font-[var(--font-heading)] text-[22px] font-bold text-[#0a0c0f]">
                    {current.search ? `“${current.search}”` : shortPage(current.page)}
                  </h2>
                  <p className="mt-1 text-xs text-[#4a5560]">
                    {current.search ? <>{shortPage(current.page)} · </> : null}
                    {itemMetricsLine(current)}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {flagsFor(current, diag).map((f) => (
                      <Pill key={f.text} t={f.t}>
                        {f.text}
                      </Pill>
                    ))}
                  </div>
                </div>

                <StyleNotesBanner styleNotes={styleNotes} clientSlug={clientSlug} compact />

                {diag?.error ? (
                  <p role="alert" className="rounded-xl border px-4 py-3 text-[13px]" style={toneStyle("miss")}>
                    {diag.error}
                  </p>
                ) : null}

                <div className="rounded-xl border border-[#ececec] bg-white p-5">
                  <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                    Ready to diagnose
                  </div>
                  <p className="mt-1.5 text-[13px] text-[#4a5560]">
                    A diagnosis takes about 20 seconds and checks:
                  </p>
                  <ul className="mt-3 grid grid-cols-1 gap-x-4 gap-y-2 text-[13px] text-[#171a22] sm:grid-cols-2">
                    {READY_CHECKS[activeFocus].map((item, idx) => (
                      <li key={item} className="flex items-start gap-2">
                        <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-[#223540] text-[11px] font-bold text-white">
                          {idx + 1}
                        </span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                  <div className="mt-4 flex flex-wrap items-center gap-2.5">
                    <button
                      type="button"
                      onClick={() => diagnose(current)}
                      className="cursor-pointer rounded-full px-5 py-2 text-[13px] font-semibold text-white"
                      style={{ background: DARK }}
                    >
                      {diag?.error ? "Try again" : "Diagnose this page"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setRejectOpen((o) => !o)}
                      className="cursor-pointer rounded-full border border-[oklch(0.88_0.06_25)] bg-white px-4 py-2 text-[13px] font-semibold text-[oklch(0.48_0.17_25)] hover:bg-[oklch(0.965_0.025_25)]"
                    >
                      {rejectOpen ? "Cancel reject" : "Reject"}
                    </button>
                  </div>
                </div>

                {rejectOpen ? (
                  <RejectForm
                    reasons={rejectionReasons}
                    busy={pending}
                    onSubmit={submitRejection}
                    onCancel={() => setRejectOpen(false)}
                  />
                ) : null}

                {(sessionRejections[current.page]?.length ?? 0) > 0 ? (
                  <PriorRejectionsCard rejections={sessionRejections[current.page]} />
                ) : null}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom monthly plan tray */}
      <div className="flex flex-wrap items-center gap-3 border-t border-[#e8e8e8] bg-white px-5 py-2.5">
        <div className="shrink-0">
          <div className="font-[var(--font-heading)] text-[13px] font-bold text-[#0a0c0f]">
            {monthName} plan
          </div>
          <div className="text-[11px] text-[#7a838c] tabular-nums">
            {planned.length}
            {allowance.monthly != null ? ` of ${allowance.monthly}` : ""} action
            {planned.length === 1 && allowance.monthly == null ? "" : "s"}
          </div>
        </div>

        <div className="flex min-w-[14rem] flex-1 gap-2 overflow-x-auto">
          {Array.from({ length: slots }, (_, i) => planned[i]).map((task, i) =>
            task ? (
              <div
                key={task.id}
                className="flex min-h-[42px] min-w-[9.5rem] flex-1 items-center gap-2 rounded-[10px] border px-2.5 py-1"
                style={{ borderColor: "#bfe9e4", background: "#f7fcfb" }}
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-semibold text-[#0a0c0f]">{task.search || shortPage(task.page)}</div>
                  <div className="truncate text-[11px] text-[#7a838c]">
                    {task.parts?.length ?? 1} task{(task.parts?.length ?? 1) === 1 ? "" : "s"} · {shortPage(task.page)}
                    {task.teamwork_task_id ? " · sent" : ""}
                  </div>
                </div>
                {task.teamwork_task_id ? null : (
                  <button
                    type="button"
                    onClick={() => remove(task)}
                    disabled={pending}
                    aria-label={`Remove ${task.search || shortPage(task.page)} from the plan`}
                    className="cursor-pointer text-[#7a838c] hover:text-red-700"
                  >
                    ×
                  </button>
                )}
              </div>
            ) : (
              <div
                key={`open-${i}`}
                className="flex min-h-[42px] min-w-[9.5rem] flex-1 items-center justify-center rounded-[10px] border border-dashed border-[#d3d7d9] bg-[#f8f8f8] text-xs text-[#7a838c]"
              >
                Open slot
              </div>
            ),
          )}
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <Link href={`/${clientSlug}/engine#plan`} className="text-xs font-semibold text-[#00857b] underline">
            Assign and track ↓
          </Link>
          <button
            type="button"
            onClick={sendAll}
            disabled={sending || unsent.length === 0 || !teamworkReady}
            title={
              teamworkReady
                ? undefined
                : "Teamwork is not set up for this client. Choose a tasklist in Settings → Connections."
            }
            className="cursor-pointer rounded-full px-[18px] py-2 text-[13px] font-semibold text-white disabled:cursor-not-allowed"
            style={{
              background:
                planned.length > 0 && unsent.length === 0
                  ? TEAL
                  : sending || unsent.length === 0 || !teamworkReady
                    ? "#c5cdd2"
                    : DARK,
            }}
          >
            {sending ? (
              <>
                <Spinner />
                Sending…
              </>
            ) : planned.length > 0 && unsent.length === 0 ? (
              "Sent to Teamwork ✓"
            ) : (
              "Send to Teamwork"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
