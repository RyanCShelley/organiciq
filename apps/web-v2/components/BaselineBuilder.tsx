"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import {
  exportBaselinePillarsCsvAction,
  loadBaselineAction,
  loadBaselineCsvAction,
  loadBaselinePillarsAction,
  lockBaselineAction,
  updateBaselineGoalAction,
} from "@/app/(app)/[clientSlug]/settings/baseline/actions";
import { resolveStepHref, type SetupState } from "@/components/SetupChecklist";
import { SaveBar, inputClass } from "@/components/ui/form";
import {
  REBASELINE_REASONS,
  conversionNoun,
  type Analysis,
  type BaselineGoalState,
  type BaselineLockResponse,
  type BaselineVersion,
  type PillarsSnapshot,
} from "@/lib/baseline";

const fmt = (n: number | null | undefined, digits = 0) =>
  n == null ? "–" : n.toLocaleString(undefined, { maximumFractionDigits: digits });

function StatCard({
  label,
  primary,
  secondary,
  footnote,
  accent = false,
}: {
  label: string;
  primary: string;
  secondary?: string;
  footnote?: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border p-3.5 ${
        accent ? "border-[var(--brand-teal)]/30 bg-white" : "border-[var(--border)] bg-[var(--background)]"
      }`}
    >
      <div className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-lg font-bold tabular-nums text-[var(--text-primary)]">{primary}</div>
      {secondary ? <div className="text-xs font-medium tabular-nums text-[var(--text-secondary)]">{secondary}</div> : null}
      {footnote ? <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">{footnote}</div> : null}
    </div>
  );
}

export function BaselineBuilder({
  clientId,
  slug,
  model,
  counted,
  defaultLeadEvents,
  versions,
  currentGoal,
  goalState,
  setup,
}: {
  clientId: string;
  slug: string;
  model: string | null;
  counted: { event: string; type: string }[];
  defaultLeadEvents?: string[];
  versions: BaselineVersion[];
  currentGoal: number | null;
  goalState?: BaselineGoalState | null;
  setup?: SetupState | null;
}) {
  const router = useRouter();
  const noun = conversionNoun(model);
  const events = counted.map((c) => c.event);
  const baselineEventsSet = new Set(events);
  const defaultEventsSet = new Set(defaultLeadEvents ?? events);

  const [sourceMode, setSourceMode] = useState<"ga4" | "csv">("ga4");
  const needsSync =
    sourceMode === "ga4" &&
    (baselineEventsSet.size !== defaultEventsSet.size ||
      events.some((e) => !defaultEventsSet.has(e)));
  const [csvText, setCsvText] = useState("");
  const [months, setMonths] = useState(24);
  const [halfLifeMonths, setHalfLifeMonths] = useState(3);
  const [regimeStart, setRegimeStart] = useState("");
  const [acknowledged, setAcknowledged] = useState<string[]>([]);

  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [pillars, setPillars] = useState<PillarsSnapshot | null>(null);
  const [showTopPages, setShowTopPages] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showPillars, setShowPillars] = useState(false);
  const [showVersions, setShowVersions] = useState(versions.length > 1);
  const [exportError, setExportError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [goal, setGoal] = useState("");
  const [trafficGoal, setTrafficGoal] = useState("");
  const [visibilityClicksGoal, setVisibilityClicksGoal] = useState("");
  const [targetRate, setTargetRate] = useState(
    goalState?.target_lead_rate_pct != null ? String(goalState.target_lead_rate_pct) : "",
  );
  const [agree, setAgree] = useState(false);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [lockPending, startLock] = useTransition();
  const [lockError, setLockError] = useState<string | null>(null);
  const [lockNotice, setLockNotice] = useState<BaselineLockResponse | null>(null);

  const [activeGoal, setActiveGoal] = useState<number | null>(goalState?.current ?? currentGoal);
  const [goalDraft, setGoalDraft] = useState<string>(
    goalState?.current != null ? String(goalState.current) : currentGoal != null ? String(currentGoal) : "",
  );
  const [goalPending, startGoalSave] = useTransition();
  const [goalMessage, setGoalMessage] = useState<string | null>(null);
  const [goalError, setGoalError] = useState<string | null>(null);

  const isFirst = versions.length === 0;
  const [open, setOpen] = useState(false);
  const formVisible = isFirst || open;

  useEffect(() => {
    const nextGoal = goalState?.current ?? currentGoal;
    setActiveGoal(nextGoal);
    if (nextGoal != null) setGoalDraft(String(nextGoal));
  }, [goalState?.current, currentGoal]);

  useEffect(() => {
    if (sourceMode === "csv") return;
    if (events.length === 0) {
      setAnalysis(null);
      setLoadError(null);
      return;
    }
    let live = true;
    setLoadError(null);
    loadBaselineAction(clientId, events, regimeStart, acknowledged, months, halfLifeMonths).then((result) => {
      if (!live) return;
      if (result.ok) setAnalysis(result.analysis);
      else {
        setAnalysis(null);
        setLoadError(result.error);
      }
    });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, sourceMode, events.join("|"), regimeStart, acknowledged.join("|"), months, halfLifeMonths]);

  useEffect(() => {
    let live = true;
    loadBaselinePillarsAction(clientId, events).then((res) => {
      if (live && res.ok) setPillars(res.pillars);
    });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, events.join("|")]);

  const switchSourceMode = (nextMode: "ga4" | "csv") => {
    if (nextMode === sourceMode) return;
    setSourceMode(nextMode);
    setAnalysis(null);
    setLoadError(null);
  };

  const runCsvAnalysis = (overrideRegime = regimeStart, overrideAck = acknowledged) => {
    if (!csvText.trim()) {
      setLoadError("Paste CSV rows (month, sessions, leads) first.");
      return;
    }
    setLoadError(null);
    loadBaselineCsvAction(clientId, csvText, overrideRegime, overrideAck, halfLifeMonths).then((result) => {
      if (result.ok) setAnalysis(result.analysis);
      else setLoadError(result.error);
    });
  };

  const applySuggestedRegime = (suggested: string) => {
    setRegimeStart(suggested);
    if (sourceMode === "csv") {
      runCsvAnalysis(suggested, acknowledged);
    }
  };

  const handleExportCsv = async (version?: number) => {
    setExportError(null);
    const res = await exportBaselinePillarsCsvAction(clientId, events, version);
    if (!res.ok) {
      setExportError(res.error);
      return;
    }
    const blob = new Blob([res.csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = version != null ? `${slug}-baseline-v${version}.csv` : `${slug}-baseline-pillars.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const saveDirectGoal = (targetGoal: number) => {
    setGoalError(null);
    setGoalMessage(null);
    startGoalSave(async () => {
      const res = await updateBaselineGoalAction(clientId, slug, targetGoal);
      if (res.ok) {
        setActiveGoal(res.goal.current);
        if (res.goal.current != null) setGoalDraft(String(res.goal.current));
        setGoalMessage(`Monthly goal updated to ${res.goal.current ?? targetGoal}/mo.`);
        router.refresh();
      } else {
        setGoalError(res.error);
      }
    });
  };

  const blockerFlags = analysis?.flags.filter((f) => f.level === "blocker") ?? [];
  const warningFlags = analysis?.flags.filter((f) => f.level === "warning") ?? [];
  const infoFlags = analysis?.flags.filter((f) => f.level === "info") ?? [];
  const openBlockers = blockerFlags.filter((f) => !acknowledged.includes(f.code));
  const hasRegimeBreakBlocker = blockerFlags.some(
    (f) => f.code === "regime_break_unconfirmed" || f.code === "tracking_gap",
  );
  const suggestedRegime = analysis?.window.suggested_regime_start ?? null;

  const pullStep = setup?.steps.find((s) => s.key === "pull");
  const pullHasGa4 = Boolean(pullStep?.detail && /GA4 through/i.test(pullStep.detail));
  const ga4NotSynced = Boolean(loadError && /no validated ga4 data|no ga4 traffic facts/i.test(loadError));
  const missingGa4Sessions = Boolean(
    ga4NotSynced ||
      (pillars &&
        pillars.traffic.total_sessions.total_90d === 0 &&
        !analysis &&
        !pullHasGa4 &&
        (events.length === 0 || Boolean(loadError))),
  );
  const missingLeadEvents = counted.length === 0;

  const channelMap = new Map((pillars?.traffic.channels ?? []).map((c) => [c.channel, c]));
  const directCh = channelMap.get("direct_unattributed");
  const aiRefCh = channelMap.get("ai_referral");
  const otherChannels = (pillars?.traffic.channels ?? []).filter(
    (c) => c.channel !== "organic_search" && c.channel !== "direct_unattributed" && c.channel !== "ai_referral",
  );

  const latestVersion = versions[0] ?? null;
  const suggestedGoal = analysis?.projection.suggested_monthly_lead_goal ?? goalState?.suggested ?? null;

  const watchlistDone = Boolean(setup?.steps.find((s) => s.key === "watchlist")?.done);
  const nextSetupStep = setup?.steps.find((s) => !s.done && !s.optional && s.key !== "baseline") ?? null;
  const postLockCta = !watchlistDone
    ? { href: `/${slug}/watchlist`, label: "Next: Build your keyword watchlist →" }
    : nextSetupStep
      ? {
          href: resolveStepHref(slug, nextSetupStep, setup?.service_mode),
          label: `Next: ${nextSetupStep.title} →`,
        }
      : { href: `/${slug}`, label: "View client overview →" };

  const lockWhy =
    openBlockers.length > 0
      ? "Check the blocker box(es) above first."
      : needsSync && !agree
        ? "Confirm the lead conversion update checkbox above first."
        : undefined;

  return (
    <div className="space-y-6">
      {/* Top-Level Post-Lock Confirmation Banner (never hidden by setOpen(false)) */}
      {lockNotice ? (
        <div
          role="status"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-green-200 bg-green-50 px-5 py-4 text-sm text-green-900"
        >
          <div>
            <p className="font-semibold">
              Baseline v{lockNotice.version.version} locked · Monthly {noun.singular} goal set to{" "}
              {lockNotice.monthly_lead_goal}/mo
            </p>
            {lockNotice.lead_conversions_changed ? (
              <p className="mt-0.5 text-xs text-green-800">
                Client lead conversion definitions were updated to match this baseline.
              </p>
            ) : null}
          </div>
          <Link
            href={postLockCta.href}
            className="rounded-lg bg-[var(--brand-teal)] px-3.5 py-2 text-xs font-semibold text-white hover:bg-[var(--brand-teal-hover)]"
          >
            {postLockCta.label}
          </Link>
        </div>
      ) : null}

      {/* Minimal Prerequisite Notice (ONLY when GA4 sessions or lead events are missing) */}
      {(missingLeadEvents || missingGa4Sessions) && sourceMode === "ga4" ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50/80 px-5 py-4 text-sm text-amber-950">
          <p className="font-semibold">
            {missingGa4Sessions
              ? "GA4 traffic data is needed to calculate your baseline"
              : `No GA4 ${noun.plural} events are marked yet`}
          </p>
          <p className="mt-1 text-xs text-amber-900">
            {missingGa4Sessions
              ? "Connect GA4 and run a data pull first, or switch to CSV input in Advanced options below."
              : "Choose at least one GA4 conversion event to model your starting baseline and 12-month goal, or switch to CSV input in Advanced options below."}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
            <Link
              href={missingGa4Sessions ? `/${slug}/settings/connections` : `/${slug}/settings/conversions`}
              className="rounded-lg bg-[var(--brand-dark)] px-3 py-1.5 font-semibold text-white"
            >
              {missingGa4Sessions ? "Go to Connections & Pull →" : "Set conversion events →"}
            </Link>
            <button
              type="button"
              onClick={() => {
                setShowAdvanced(true);
                switchSourceMode("csv");
              }}
              className="font-semibold text-[var(--brand-teal)] hover:underline"
            >
              Use CSV fallback instead
            </button>
          </div>
        </div>
      ) : null}

      {/* Current Locked Baseline Card (when locked) */}
      {latestVersion ? (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold">Current Locked Baseline (v{latestVersion.version})</h2>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                    latestVersion.status === "provisional"
                      ? "bg-amber-100 text-amber-800"
                      : "bg-green-100 text-green-800"
                  }`}
                >
                  {latestVersion.status}
                </span>
              </div>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">
                Window: {latestVersion.window_from} to {latestVersion.window_to}
                {latestVersion.regime_start ? ` · Regime start ${latestVersion.regime_start}` : ""}
                {latestVersion.lead_events.length ? ` · Events: ${latestVersion.lead_events.join(", ")}` : ""}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {latestVersion.has_pillars ? (
                <button
                  type="button"
                  onClick={() => handleExportCsv(latestVersion.version)}
                  className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-xs font-semibold hover:bg-[var(--background)]"
                >
                  Export CSV
                </button>
              ) : null}
              {!open ? (
                <button
                  type="button"
                  onClick={() => {
                    setLockNotice(null);
                    setOpen(true);
                  }}
                  className="rounded-lg bg-[var(--brand-dark)] px-3 py-1.5 text-xs font-semibold text-white"
                >
                  Re-baseline
                </button>
              ) : null}
              <Link
                href={`/${slug}/watchlist`}
                className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-xs font-semibold text-[var(--brand-teal)] hover:bg-[var(--background)]"
              >
                Watchlist →
              </Link>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Baseline sessions / mo"
              primary={fmt(latestVersion.monthly_sessions)}
              secondary={
                latestVersion.monthly_organic_sessions != null
                  ? `Organic: ${fmt(latestVersion.monthly_organic_sessions)}/mo`
                  : undefined
              }
            />
            <StatCard
              label={`Baseline ${noun.plural} / mo`}
              primary={fmt(latestVersion.monthly_leads, 1)}
              secondary={
                latestVersion.lead_rate_pct != null ? `${fmt(latestVersion.lead_rate_pct, 2)}% rate` : undefined
              }
            />
            <StatCard
              accent
              label={`Active monthly ${noun.singular} goal`}
              primary={activeGoal != null ? `${fmt(activeGoal)}/mo` : "Not set"}
              secondary={
                (latestVersion.goals?.monthly_traffic ?? goalState?.pillar_goals?.monthly_traffic) != null
                  ? `Traffic goal: ${fmt(latestVersion.goals?.monthly_traffic ?? goalState?.pillar_goals?.monthly_traffic)}/mo`
                  : goalState?.suggested != null
                    ? `12-mo suggested: ${fmt(goalState.suggested)}/mo`
                    : undefined
              }
              footnote={
                (latestVersion.goals?.monthly_visibility_clicks ?? goalState?.pillar_goals?.monthly_visibility_clicks) != null
                  ? `Visibility goal: ${fmt(latestVersion.goals?.monthly_visibility_clicks ?? goalState?.pillar_goals?.monthly_visibility_clicks)} clicks/mo`
                  : undefined
              }
            />
            <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-3.5 space-y-2">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
                Update monthly goal
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={0}
                  value={goalDraft}
                  onChange={(e) => {
                    setGoalDraft(e.target.value);
                    setGoalMessage(null);
                    setGoalError(null);
                  }}
                  aria-label={`Monthly ${noun.singular} goal`}
                  className="w-24 rounded-lg border border-[var(--border)] bg-white px-2.5 py-1.5 text-sm tabular-nums"
                />
                <button
                  type="button"
                  disabled={goalPending || !goalDraft.trim()}
                  onClick={() => saveDirectGoal(Number(goalDraft))}
                  className="rounded-lg bg-[var(--brand-teal)] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {goalPending ? "Saving…" : "Update"}
                </button>
              </div>
              {goalState?.suggested != null && goalState.suggested !== activeGoal ? (
                <button
                  type="button"
                  disabled={goalPending}
                  onClick={() => saveDirectGoal(goalState.suggested!)}
                  className="text-[11px] font-semibold text-[var(--brand-teal)] hover:underline disabled:opacity-50"
                >
                  Align to suggested ({goalState.suggested}/mo)
                </button>
              ) : null}
              {goalMessage ? <p className="text-[11px] text-green-700">{goalMessage}</p> : null}
              {goalError ? <p className="text-[11px] text-red-700">{goalError}</p> : null}
            </div>
          </div>
        </div>
      ) : null}

      {/* Step-by-Step Review & Lock Flow (only shown during initial setup or Re-baseline) */}
      {formVisible && analysis ? (
        <div className="space-y-4">
          <div className="rounded-xl border border-[var(--brand-teal)]/30 bg-[var(--brand-teal-soft)]/20 px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                  {isFirst ? "Set your starting baseline in 3 steps" : `Re-baseline workflow (v${versions.length + 1})`}
                </h2>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  Review your starting data, check the 12-month model, and lock a benchmark so future progress is measured cleanly.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold text-[var(--text-secondary)]">
                <span className="rounded-full bg-white px-2.5 py-1 border border-[var(--border)]">1. Verify data</span>
                <span aria-hidden="true">→</span>
                <span className="rounded-full bg-white px-2.5 py-1 border border-[var(--border)]">2. Review projection</span>
                <span aria-hidden="true">→</span>
                <span className="rounded-full bg-white px-2.5 py-1 border border-[var(--border)]">3. Lock baseline</span>
              </div>
            </div>
          </div>

          {/* Step 1: Verify your starting data & flags */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wide text-[var(--brand-teal)]">
                  Step 1 of 3
                </div>
                <h3 className="text-base font-semibold">Verify your starting data</h3>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                  Confirm we&apos;re counting the right {noun.plural} events and a clean historical window before locking.
                </p>
              </div>
              <Link
                href={`/${slug}/settings/conversions`}
                className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--background)]"
              >
                Edit conversion events
              </Link>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] px-4 py-3 text-xs">
                <div className="font-semibold text-[var(--text-tertiary)] uppercase tracking-wide text-[11px]">
                  Evaluated window
                </div>
                <div className="mt-1 font-semibold text-[var(--text-primary)]">
                  {analysis.window.from} to {analysis.window.to} ({analysis.window.months} month
                  {analysis.window.months === 1 ? "" : "s"})
                </div>
                {analysis.window.regime_start ? (
                  <div className="mt-0.5 text-[var(--text-secondary)]">Regime start: {analysis.window.regime_start}</div>
                ) : null}
              </div>
              <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] px-4 py-3 text-xs">
                <div className="font-semibold text-[var(--text-tertiary)] uppercase tracking-wide text-[11px]">
                  Counted GA4 {noun.plural} events
                </div>
                <div className="mt-1 font-semibold text-[var(--text-primary)]">
                  {events.length > 0 ? events.join(", ") : "None selected"}
                </div>
              </div>
            </div>

            {/* Flags: Blockers, Warnings, Info */}
            {blockerFlags.length > 0 ? (
              <div className="rounded-xl border border-red-200 bg-red-50 p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-sm font-semibold text-red-800">Review required before locking</h4>
                  {hasRegimeBreakBlocker && suggestedRegime && regimeStart !== suggestedRegime ? (
                    <button
                      type="button"
                      onClick={() => applySuggestedRegime(suggestedRegime)}
                      className="rounded-lg bg-red-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-800"
                    >
                      Use suggested start ({suggestedRegime})
                    </button>
                  ) : null}
                </div>
                <ul className="space-y-2 text-sm text-red-800">
                  {blockerFlags.map((flag) => (
                    <li key={flag.code} className="flex items-start justify-between gap-3">
                      <span>{flag.message}</span>
                      <label className="flex shrink-0 items-center gap-1.5 text-xs font-medium">
                        <input
                          type="checkbox"
                          checked={acknowledged.includes(flag.code)}
                          onChange={(e) =>
                            setAcknowledged((current) =>
                              e.target.checked
                                ? current.includes(flag.code)
                                  ? current
                                  : [...current, flag.code]
                                : current.filter((c) => c !== flag.code),
                            )
                          }
                        />
                        I have checked this
                      </label>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {warningFlags.length > 0 ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50/70 p-3.5 text-xs text-amber-950 space-y-1">
                <div className="font-semibold">Warnings</div>
                <ul className="list-disc pl-4 space-y-1">
                  {warningFlags.map((flag) => (
                    <li key={flag.code}>{flag.message}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {infoFlags.length > 0 ? (
              <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-3.5 text-xs text-[var(--text-secondary)] space-y-1">
                <div className="font-semibold text-[var(--text-primary)]">Notes</div>
                <ul className="list-disc pl-4 space-y-1">
                  {infoFlags.map((flag) => (
                    <li key={flag.code}>{flag.message}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>

          {/* Step 2: Modeled Baseline & 12-Month Growth Projections */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wide text-[var(--brand-teal)]">
                  Step 2 of 3
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-base font-semibold">Modeled Baseline &amp; 12-Month Projection</h3>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                      analysis.status === "provisional"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-[var(--brand-teal-soft)] text-[var(--brand-dark)]"
                    }`}
                  >
                    {analysis.status}
                  </span>
                  <span className="rounded-full bg-[var(--background)] px-2 py-0.5 text-[11px] font-semibold text-[var(--text-secondary)]">
                    {analysis.projection.plan_label} plan
                  </span>
                </div>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                  Your starting benchmark weights recent months more heavily, then projects realistic 12-month growth.
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                accent
                label="Modeled sessions / mo"
                primary={fmt(analysis.baseline.monthly_sessions)}
                secondary={`Range: ${fmt(analysis.ranges.monthly_sessions.low)} – ${fmt(analysis.ranges.monthly_sessions.high)}`}
                footnote={`±${analysis.ranges.monthly_sessions.pct}% typical band`}
              />
              <StatCard
                label="Modeled organic / mo"
                primary={fmt(analysis.baseline.monthly_organic_sessions)}
                secondary={
                  analysis.ranges.monthly_organic_sessions
                    ? `Range: ${fmt(analysis.ranges.monthly_organic_sessions.low)} – ${fmt(analysis.ranges.monthly_organic_sessions.high)}`
                    : undefined
                }
                footnote={
                  analysis.ranges.monthly_organic_sessions
                    ? `±${analysis.ranges.monthly_organic_sessions.pct}% typical band`
                    : "Organic split unavailable"
                }
              />
              <StatCard
                label={`${noun.singular[0].toUpperCase()}${noun.singular.slice(1)} rate`}
                primary={`${fmt(analysis.baseline.lead_rate_pct, 2)}%`}
                secondary={`Range: ${fmt(analysis.ranges.lead_rate_pct.low, 2)}% – ${fmt(analysis.ranges.lead_rate_pct.high, 2)}%`}
                footnote={`±${analysis.ranges.lead_rate_pct.pct}% typical band`}
              />
              <StatCard
                accent
                label={`Modeled ${noun.plural} / mo`}
                primary={fmt(analysis.baseline.monthly_leads, 1)}
                secondary={`Range: ${fmt(analysis.ranges.monthly_leads.low, 1)} – ${fmt(analysis.ranges.monthly_leads.high, 1)}`}
                footnote={analysis.ranges.note}
              />
            </div>

            {/* 12-Month Growth Projection Checkpoints */}
            <div className="space-y-3 border-t border-[var(--border)] pt-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
                    {analysis.projection.goal_horizon_months}-Month Growth Projection ({analysis.projection.plan_label})
                  </h4>
                  <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{analysis.projection.disclaimer}</p>
                </div>
                <div className="rounded-lg border border-[var(--brand-teal)]/30 bg-[var(--brand-teal-soft)]/25 px-3 py-1.5 text-xs">
                  Suggested monthly goal:{" "}
                  <strong className="tabular-nums text-[var(--text-primary)]">
                    {analysis.projection.suggested_monthly_lead_goal}/mo
                  </strong>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-5">
                {analysis.projection.checkpoints.map((cp) => (
                  <StatCard
                    key={cp.month}
                    accent={cp.month === analysis.projection.goal_horizon_months}
                    label={cp.label}
                    primary={`${fmt(cp.monthly_leads, 1)} ${noun.plural}`}
                    secondary={`${fmt(cp.monthly_sessions)} sessions${cp.monthly_gsc_clicks != null ? ` · ${fmt(cp.monthly_gsc_clicks)} clicks` : ""}`}
                    footnote={`${fmt(cp.lead_rate_pct, 2)}% rate${cp.ai_visibility_pct != null ? ` · ${cp.ai_visibility_pct}% AI` : ""}`}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* Simple Monthly Goal + Lock Baseline Form */}
      {analysis && formVisible ? (
        <form
          className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            setLockError(null);
            setLockNotice(null);
            startLock(async () => {
              const result = await lockBaselineAction(clientId, slug, {
                source: sourceMode,
                csv_text: sourceMode === "csv" ? csvText : null,
                months,
                half_life_months: halfLifeMonths,
                lead_events: events,
                regime_start: regimeStart || null,
                acknowledged,
                reason_code: isFirst ? null : reason,
                reason_note: isFirst ? null : note.trim() || null,
                monthly_lead_goal: goal.trim() ? Number(goal) : null,
                monthly_traffic_goal: trafficGoal.trim() ? Number(trafficGoal) : null,
                monthly_visibility_clicks_goal: visibilityClicksGoal.trim() ? Number(visibilityClicksGoal) : null,
                target_lead_rate_pct: targetRate.trim() ? Number(targetRate) : null,
                sync_lead_conversions: agree,
              });
              if (result.ok) {
                setLockNotice(result.data);
                setActiveGoal(result.data.monthly_lead_goal);
                setGoalDraft(String(result.data.monthly_lead_goal));
                setOpen(false);
                setGoal("");
                setTrafficGoal("");
                setVisibilityClicksGoal("");
                setReason("");
                setNote("");
                setAgree(false);
                router.refresh();
              } else setLockError(result.error);
            });
          }}
        >
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wide text-[var(--brand-teal)]">
              Step 3 of 3
            </div>
            <h2 className="text-sm font-semibold">{isFirst ? "Confirm monthly goal & lock baseline" : "Create a new baseline"}</h2>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Saves the modeled baseline and 3-pillar snapshot as version {versions.length + 1}. Locked baselines never change.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <label className="block text-sm">
              <span className="font-semibold">12-month monthly {noun.singular} goal</span>
              <input
                type="number"
                min={0}
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder={
                  suggestedGoal != null
                    ? `Default: ${suggestedGoal} (12-mo projection)`
                    : currentGoal != null
                      ? `Current: ${currentGoal}`
                      : "Uses 12-mo projection"
                }
                className={`${inputClass} mt-1`}
              />
              {suggestedGoal != null ? (
                <span className="mt-1 block text-xs text-[var(--text-secondary)]">
                  Leave blank to use {suggestedGoal}/mo.
                </span>
              ) : null}
            </label>
            <label className="block text-sm">
              <span className="font-semibold">12-month traffic goal (sessions/mo)</span>
              <input
                type="number"
                min={0}
                value={trafficGoal}
                onChange={(e) => setTrafficGoal(e.target.value)}
                placeholder={
                  analysis.projection.suggested_monthly_traffic_goal != null
                    ? `Default: ${analysis.projection.suggested_monthly_traffic_goal}`
                    : "Optional"
                }
                className={`${inputClass} mt-1`}
              />
              {analysis.projection.suggested_monthly_traffic_goal != null ? (
                <span className="mt-1 block text-xs text-[var(--text-secondary)]">
                  Leave blank to use {fmt(analysis.projection.suggested_monthly_traffic_goal)}/mo.
                </span>
              ) : null}
            </label>
            <label className="block text-sm">
              <span className="font-semibold">12-month visibility goal (GSC clicks/mo)</span>
              <input
                type="number"
                min={0}
                value={visibilityClicksGoal}
                onChange={(e) => setVisibilityClicksGoal(e.target.value)}
                placeholder={
                  analysis.projection.suggested_monthly_visibility_clicks_goal != null
                    ? `Default: ${analysis.projection.suggested_monthly_visibility_clicks_goal}`
                    : "Optional"
                }
                className={`${inputClass} mt-1`}
              />
              {analysis.projection.suggested_monthly_visibility_clicks_goal != null ? (
                <span className="mt-1 block text-xs text-[var(--text-secondary)]">
                  Leave blank to use {fmt(analysis.projection.suggested_monthly_visibility_clicks_goal)}/mo.
                </span>
              ) : null}
            </label>
          </div>

          {!isFirst ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm">
                <span className="font-semibold">Why a new baseline?</span>
                <select value={reason} onChange={(e) => setReason(e.target.value)} required className={`${inputClass} mt-1`}>
                  <option value="" disabled>
                    Choose a reason
                  </option>
                  {REBASELINE_REASONS.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : null}

          {!isFirst ? (
            <label className="block text-sm">
              <span className="font-semibold">Say why, in a sentence</span>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} required minLength={10} className={`${inputClass} mt-1`} />
            </label>
          ) : null}

          {needsSync ? (
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1" />
              <span>Update the client&apos;s lead conversions to match what this baseline counted.</span>
            </label>
          ) : null}

          <SaveBar
            pending={lockPending}
            saved={false}
            error={lockError}
            label={`Lock as version ${versions.length + 1}`}
            disabled={openBlockers.length > 0 || (needsSync && !agree)}
            why={lockWhy}
          />
          {!isFirst ? (
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-sm text-[var(--text-secondary)] hover:underline"
            >
              Cancel
            </button>
          ) : null}
        </form>
      ) : null}

      {/* Advanced options & monthly series (collapsed by default, only shown when reviewing/locking or in CSV mode) */}
      {(formVisible || sourceMode === "csv") ? (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)]">
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          aria-expanded={showAdvanced}
          className="flex w-full items-center justify-between gap-3 px-6 py-3.5 text-left text-xs"
        >
          <span className="font-semibold text-[var(--text-primary)]">
            Advanced options &amp; monthly series
          </span>
          <span className="font-semibold text-[var(--brand-teal)]">
            {showAdvanced ? "Hide" : "Show"}
          </span>
        </button>

        {showAdvanced ? (
          <div className="space-y-5 border-t border-[var(--border)] p-6 text-sm">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <label className="block text-xs">
                <span className="font-semibold">Regime start (optional)</span>
                <div className="mt-1 flex items-center gap-2">
                  <input
                    type="month"
                    value={regimeStart}
                    onChange={(e) => setRegimeStart(e.target.value)}
                    className={inputClass}
                  />
                  {regimeStart ? (
                    <button
                      type="button"
                      onClick={() => setRegimeStart("")}
                      className="text-xs font-semibold text-[var(--text-secondary)] hover:underline"
                    >
                      Clear
                    </button>
                  ) : null}
                </div>
                {suggestedRegime && regimeStart !== suggestedRegime ? (
                  <button
                    type="button"
                    onClick={() => applySuggestedRegime(suggestedRegime)}
                    className="mt-1 text-[11px] font-semibold text-[var(--brand-teal)] hover:underline"
                  >
                    Use suggested ({suggestedRegime})
                  </button>
                ) : null}
              </label>

              <label className="block text-xs">
                <span className="font-semibold">Lookback months</span>
                <select
                  value={months}
                  onChange={(e) => setMonths(Number(e.target.value))}
                  disabled={sourceMode === "csv"}
                  className={`${inputClass} mt-1`}
                >
                  <option value={12}>12 months</option>
                  <option value={24}>24 months</option>
                  <option value={36}>36 months</option>
                </select>
              </label>

              <label className="block text-xs">
                <span className="font-semibold">Recency half-life (months)</span>
                <input
                  type="number"
                  min={0.5}
                  max={24}
                  step={0.5}
                  value={halfLifeMonths}
                  onChange={(e) => setHalfLifeMonths(Number(e.target.value) || 3)}
                  className={`${inputClass} mt-1`}
                />
              </label>

              <label className="block text-xs">
                <span className="font-semibold">Target {noun.singular} rate % (optional)</span>
                <input
                  type="number"
                  min={0.01}
                  max={100}
                  step={0.1}
                  value={targetRate}
                  onChange={(e) => setTargetRate(e.target.value)}
                  placeholder={goalState?.target_lead_rate_pct != null ? `${goalState.target_lead_rate_pct}%` : "Optional"}
                  className={`${inputClass} mt-1`}
                />
              </label>
            </div>

            <div className="border-t border-[var(--border)] pt-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-semibold text-[var(--text-primary)]">Data source</span>
                <div className="flex items-center gap-2 text-xs">
                  <button
                    type="button"
                    onClick={() => switchSourceMode("ga4")}
                    className={`rounded-lg px-2.5 py-1 font-semibold ${
                      sourceMode === "ga4"
                        ? "bg-[var(--brand-dark)] text-white"
                        : "border border-[var(--border)] bg-white text-[var(--text-secondary)]"
                    }`}
                  >
                    GA4
                  </button>
                  <button
                    type="button"
                    onClick={() => switchSourceMode("csv")}
                    className={`rounded-lg px-2.5 py-1 font-semibold ${
                      sourceMode === "csv"
                        ? "bg-[var(--brand-dark)] text-white"
                        : "border border-[var(--border)] bg-white text-[var(--text-secondary)]"
                    }`}
                  >
                    CSV fallback
                  </button>
                </div>
              </div>

              {sourceMode === "csv" ? (
                <div className="space-y-2">
                  <textarea
                    value={csvText}
                    onChange={(e) => setCsvText(e.target.value)}
                    rows={4}
                    placeholder={"month,sessions,leads\n2026-06,1200,18\n2026-07,1350,21"}
                    className={inputClass}
                  />
                  <button
                    type="button"
                    onClick={() => runCsvAnalysis()}
                    className="rounded-lg bg-[var(--brand-teal)] px-3 py-1.5 text-xs font-semibold text-white"
                  >
                    Analyze CSV
                  </button>
                </div>
              ) : null}
            </div>

            {analysis && analysis.series.length > 0 ? (
              <div className="border-t border-[var(--border)] pt-4 space-y-2">
                <div className="text-xs font-semibold text-[var(--text-primary)]">
                  Monthly series ({analysis.series.length} months)
                </div>
                <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b border-[var(--border)] bg-[var(--background)] text-[var(--text-secondary)]">
                      <tr>
                        <th className="px-3 py-2 font-semibold">Month</th>
                        <th className="px-3 py-2 text-right font-semibold">Sessions</th>
                        <th className="px-3 py-2 text-right font-semibold">Organic</th>
                        <th className="px-3 py-2 text-right font-semibold">{noun.plural}</th>
                        <th className="px-3 py-2 text-right font-semibold">Rate</th>
                        <th className="px-3 py-2 text-right font-semibold">Window</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border)]">
                      {analysis.series.map((row) => (
                        <tr key={row.month} className={row.in_window ? "" : "opacity-55"}>
                          <td className="px-3 py-1.5 font-medium tabular-nums">{row.month}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums">{fmt(row.sessions)}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums">{fmt(row.organic_sessions)}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums">{fmt(row.leads)}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums">
                            {row.lead_rate_pct != null ? `${fmt(row.lead_rate_pct, 2)}%` : "–"}
                          </td>
                          <td className="px-3 py-1.5 text-right">
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                                row.in_window
                                  ? "bg-green-100 text-green-800"
                                  : "bg-[var(--background)] text-[var(--text-tertiary)]"
                              }`}
                            >
                              {row.in_window ? "In window" : "Excluded"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
      ) : null}

      {/* 3-Pillar Current Snapshot (collapsible reference view) */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)]">
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4">
          <button
            type="button"
            onClick={() => setShowPillars((v) => !v)}
            aria-expanded={showPillars}
            className="flex flex-1 items-center justify-between gap-3 text-left"
          >
            <div>
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">Current 3-Pillar Snapshot</h2>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                {pillars
                  ? `30d avg: ${fmt(pillars.visibility.gsc.clicks.avg_30d)} GSC clicks · ${fmt(pillars.traffic.organic_sessions.avg_30d)} organic sessions · ${fmt(pillars.leads.total.avg_30d)} ${noun.plural}`
                  : "Current 30d/90d snapshot across Visibility, Traffic, and Conversions"}
              </p>
            </div>
            <span className="text-xs font-semibold text-[var(--brand-teal)]">
              {showPillars ? "Hide" : "Show"}
            </span>
          </button>
          <button
            type="button"
            onClick={() => handleExportCsv()}
            disabled={!pillars}
            className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-xs font-semibold hover:bg-[var(--background)] disabled:opacity-50"
          >
            Export CSV
          </button>
        </div>

        {exportError ? <p role="alert" className="px-6 pb-3 text-xs text-red-700">{exportError}</p> : null}
        {loadError && !missingGa4Sessions ? (
          <p role="alert" className="mx-6 mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">
            {loadError}
          </p>
        ) : null}

        {showPillars ? (
          <div className="border-t border-[var(--border)] p-6 space-y-6">
            <p className="text-xs text-[var(--text-secondary)]">
              Current 30d/90d snapshot across Visibility, Traffic, and {noun.plural}
              {events.length > 0 ? (
                <>
                  {" "}
                  (counting <strong>{events.join(", ")}</strong> from GA4)
                </>
              ) : null}
              .{pillars ? ` Window: ${pillars.window.start_90d} to ${pillars.window.as_of}.` : ""}
              {model == null ? (
                <>
                  {" "}
                  No business type set yet —{" "}
                  <Link href={`/${slug}/settings`} className="font-semibold text-[var(--brand-teal)] hover:underline">
                    set it in General
                  </Link>
                  .
                </>
              ) : null}
            </p>
            {!pillars ? (
              <p className="text-sm text-[var(--text-secondary)]">Loading 3-pillar snapshot…</p>
            ) : (
              <div className="space-y-6">
            {/* Step 1: Visibility */}
            <section className="space-y-2.5">
              <div className="flex items-baseline justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
                  1. Visibility
                </h3>
                <span className="text-xs text-[var(--text-tertiary)]">Search, AI &amp; site readiness</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <StatCard
                  label="Google Search Console"
                  primary={`${fmt(pillars.visibility.gsc.clicks.avg_30d)} clicks / 30d`}
                  secondary={`${fmt(pillars.visibility.gsc.clicks.total_90d)} clicks (90d) · ${fmt(pillars.visibility.gsc.impressions.avg_30d)} impr / 30d`}
                  footnote={`90d Impr: ${fmt(pillars.visibility.gsc.impressions.total_90d)} · CTR: ${pillars.visibility.gsc.ctr_90d_pct ?? "–"}% · Pos: ${pillars.visibility.gsc.avg_position_90d ?? "–"}`}
                />
                <StatCard
                  label="Bing Webmaster"
                  primary={`${fmt(pillars.visibility.bing.clicks.avg_30d)} clicks / 30d`}
                  secondary={`${fmt(pillars.visibility.bing.clicks.total_90d)} clicks (90d) · ${fmt(pillars.visibility.bing.impressions.avg_30d)} impr / 30d`}
                  footnote={`90d Impr: ${fmt(pillars.visibility.bing.impressions.total_90d)} · Avg pos: ${pillars.visibility.bing.avg_position_90d ?? "–"}`}
                />
                <StatCard
                  label="Watchlist & Rankings"
                  primary={`${pillars.visibility.watchlist.tracked_keywords} tracked keywords`}
                  secondary={`${pillars.visibility.watchlist.paired_ai_prompts} paired AI prompts`}
                  footnote={`Top 3: ${pillars.visibility.watchlist.top_3} · Top 10: ${pillars.visibility.watchlist.top_10} · Avg pos: ${pillars.visibility.watchlist.avg_position ?? "–"}`}
                />
                <StatCard
                  label="LLM Visibility & SoV"
                  primary={`${pillars.visibility.llm.visibility_rate_pct ?? "–"}% visible`}
                  secondary={`Share of voice: ${pillars.visibility.llm.share_of_voice_pct ?? "–"}%`}
                  footnote={`Mentions: ${pillars.visibility.llm.mentions ?? "–"} · Citations: ${pillars.visibility.llm.citations ?? "–"}${pillars.visibility.llm.run_date ? ` · Run ${pillars.visibility.llm.run_date}` : ""}`}
                />
                <StatCard
                  label="SEO Health"
                  primary={pillars.visibility.site_health.seo_score != null ? `${pillars.visibility.site_health.seo_score}/100` : "–"}
                  secondary="Technical & on-page crawl"
                  footnote={pillars.visibility.site_health.crawl_date ? `Crawled ${pillars.visibility.site_health.crawl_date}` : "No crawl yet"}
                />
                <StatCard
                  label="GEO Health"
                  primary={pillars.visibility.site_health.geo_score != null ? `${pillars.visibility.site_health.geo_score}/100` : "–"}
                  secondary="AI & generative readiness"
                  footnote={pillars.visibility.site_health.crawl_date ? `Crawled ${pillars.visibility.site_health.crawl_date}` : "No crawl yet"}
                />
              </div>
            </section>

            {/* Step 2: Traffic */}
            <section className="space-y-2.5 border-t border-[var(--border)] pt-5">
              <div className="flex items-baseline justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
                  2. Traffic (GA4)
                </h3>
                <span className="text-xs text-[var(--text-tertiary)]">Total sessions &amp; key discovery channels</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard
                  accent
                  label="Total Sessions"
                  primary={`${fmt(pillars.traffic.total_sessions.avg_30d)} / 30d`}
                  secondary={`${fmt(pillars.traffic.total_sessions.total_90d)} (90d total)`}
                  footnote={`Last 30d: ${fmt(pillars.traffic.total_sessions.recent_30d)}`}
                />
                <StatCard
                  label="Organic Search"
                  primary={`${fmt(pillars.traffic.organic_sessions.avg_30d)} / 30d`}
                  secondary={`${fmt(pillars.traffic.organic_sessions.total_90d)} (90d total)`}
                  footnote={`Last 30d: ${fmt(pillars.traffic.organic_sessions.recent_30d)}`}
                />
                <StatCard
                  label="Direct"
                  primary={`${fmt(directCh?.avg_30d ?? 0)} / 30d`}
                  secondary={`${fmt(directCh?.total_90d ?? 0)} (90d total)`}
                  footnote={`Last 30d: ${fmt(directCh?.recent_30d ?? 0)}`}
                />
                <StatCard
                  label="AI Referral"
                  primary={`${fmt(aiRefCh?.avg_30d ?? 0)} / 30d`}
                  secondary={`${fmt(aiRefCh?.total_90d ?? 0)} (90d total)`}
                  footnote={`Last 30d: ${fmt(aiRefCh?.recent_30d ?? 0)}`}
                />
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 pt-1 text-xs text-[var(--text-secondary)]">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                  {otherChannels.map((ch) => (
                    <span key={ch.channel}>
                      <span className="capitalize text-[var(--text-tertiary)]">{ch.channel.replace(/_/g, " ")}:</span>{" "}
                      <strong className="tabular-nums">{fmt(ch.avg_30d)}</strong>/30d ({fmt(ch.total_90d)} 90d)
                    </span>
                  ))}
                </div>
                {pillars.traffic.top_pages.length > 0 ? (
                  <button
                    type="button"
                    onClick={() => setShowTopPages((v) => !v)}
                    className="font-semibold text-[var(--brand-teal)] hover:underline"
                  >
                    {showTopPages ? "Hide top pages" : `Show top ${pillars.traffic.top_pages.length} landing pages`}
                  </button>
                ) : null}
              </div>

              {showTopPages && pillars.traffic.top_pages.length > 0 ? (
                <div className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--background)]">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b border-[var(--border)] text-[var(--text-tertiary)]">
                      <tr>
                        <th className="px-3 py-2 font-semibold">Landing page</th>
                        <th className="px-3 py-2 text-right font-semibold">30-Day Avg</th>
                        <th className="px-3 py-2 text-right font-semibold">Last 30 Days</th>
                        <th className="px-3 py-2 text-right font-semibold">90-Day Total</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border)]">
                      {pillars.traffic.top_pages.map((pg) => (
                        <tr key={pg.url}>
                          <td className="px-3 py-1.5 font-medium text-[var(--text-primary)]">{pg.url}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums">{fmt(pg.avg_30d)}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums">{fmt(pg.recent_30d)}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums">{fmt(pg.total_90d)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </section>

            {/* Step 3: Conversions */}
            <section className="space-y-2.5 border-t border-[var(--border)] pt-5">
              <div className="flex items-baseline justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
                  3. {noun.plural}
                </h3>
                <span className="text-xs text-[var(--text-tertiary)]">GA4 conversion events</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard
                  accent
                  label={`Total ${noun.plural}`}
                  primary={`${fmt(pillars.leads.total.avg_30d)} / 30d`}
                  secondary={`${fmt(pillars.leads.total.total_90d)} (90d total)`}
                  footnote={`Last 30d: ${fmt(pillars.leads.total.recent_30d)}`}
                />
                <StatCard
                  label="Conversion Rate"
                  primary={pillars.leads.lead_rate_90d_pct != null ? `${pillars.leads.lead_rate_90d_pct}% (90d)` : "–"}
                  secondary={pillars.leads.lead_rate_30d_pct != null ? `${pillars.leads.lead_rate_30d_pct}% (last 30d)` : undefined}
                  footnote="Conversions / total sessions"
                />
                {pillars.leads.by_event.map((ev) => (
                  <StatCard
                    key={ev.event_name}
                    label={ev.event_name}
                    primary={`${fmt(ev.avg_30d)} / 30d`}
                    secondary={`${fmt(ev.total_90d)} (90d total)`}
                    footnote={`Last 30d: ${fmt(ev.recent_30d)}`}
                  />
                ))}
              </div>
            </section>
              </div>
            )}
          </div>
        ) : null}
      </div>

      {/* Locked Versions */}
      {versions.length > 0 ? (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)]">
          <button
            type="button"
            onClick={() => setShowVersions((v) => !v)}
            aria-expanded={showVersions}
            className="flex w-full items-center justify-between gap-3 px-6 py-4 text-left"
          >
            <div>
              <h2 className="text-sm font-semibold">Locked Versions ({versions.length})</h2>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                Historical baseline snapshots and CSV exports
              </p>
            </div>
            <span className="text-xs font-semibold text-[var(--brand-teal)]">
              {showVersions ? "Hide" : "Show"}
            </span>
          </button>
          {showVersions ? (
            <div className="border-t border-[var(--border)] p-6">
              <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-[var(--border)] bg-[var(--background)] text-[var(--text-secondary)]">
                <tr>
                  <th className="px-3 py-2 font-semibold">Version</th>
                  <th className="px-3 py-2 font-semibold">Window</th>
                  <th className="px-3 py-2 font-semibold">Reason</th>
                  <th className="px-3 py-2 font-semibold">Summary</th>
                  <th className="px-3 py-2 font-semibold">Locked</th>
                  <th className="px-3 py-2 text-right font-semibold">Export</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {versions.map((v) => (
                  <tr key={v.version}>
                    <td className="px-3 py-2.5 font-semibold whitespace-nowrap">
                      v{v.version}
                      {v.status === "provisional" ? (
                        <span className="ml-1.5 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">
                          provisional
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2.5 text-[var(--text-secondary)] whitespace-nowrap">
                      <div>
                        {v.window_from} – {v.window_to}
                      </div>
                      {v.regime_start ? (
                        <div className="text-[11px] text-[var(--text-tertiary)]">Regime: {v.regime_start}</div>
                      ) : null}
                    </td>
                    <td className="px-3 py-2.5 text-[var(--text-secondary)]">
                      <span className="capitalize">{v.reason_code.replace(/_/g, " ")}</span>
                      {v.reason_note ? <div className="text-[11px] text-[var(--text-tertiary)]">&ldquo;{v.reason_note}&rdquo;</div> : null}
                    </td>
                    <td className="px-3 py-2.5 text-[var(--text-secondary)]">
                      <div>
                        {fmt(v.monthly_leads, 1)} {noun.plural}/mo · {fmt(v.monthly_sessions)} sessions/mo
                        {v.lead_rate_pct != null ? ` · ${fmt(v.lead_rate_pct, 2)}% rate` : ""}
                      </div>
                      <div className="text-[11px] text-[var(--text-tertiary)]">Events: {v.lead_events.join(", ")}</div>
                    </td>
                    <td className="px-3 py-2.5 text-[var(--text-secondary)] whitespace-nowrap">
                      <div>{v.locked_at ? new Date(v.locked_at).toLocaleDateString() : "–"}</div>
                      <div className="text-[11px] text-[var(--text-tertiary)]">{v.locked_by}</div>
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      {v.has_pillars ? (
                        <button
                          type="button"
                          onClick={() => handleExportCsv(v.version)}
                          className="rounded border border-[var(--border)] bg-white px-2.5 py-1 font-semibold hover:bg-[var(--background)]"
                        >
                          Export CSV
                        </button>
                      ) : (
                        <span className="text-[var(--text-tertiary)]">Legacy</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
