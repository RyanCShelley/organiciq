"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import {
  exportBaselinePillarsCsvAction,
  loadBaselineAction,
  loadBaselinePillarsAction,
  lockBaselineAction,
} from "@/app/(app)/[clientSlug]/settings/baseline/actions";
import { SaveBar, inputClass } from "@/components/ui/form";
import {
  REBASELINE_REASONS,
  conversionNoun,
  type Analysis,
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
        accent ? "border-[var(--brand-teal)]/30 bg-white" : "border-[var(--border)] bg-[var(--bg)]"
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
  versions,
  currentGoal,
}: {
  clientId: string;
  slug: string;
  model: string | null;
  counted: { event: string; type: string }[];
  versions: BaselineVersion[];
  currentGoal: number | null;
}) {
  const noun = conversionNoun(model);
  const events = counted.map((c) => c.event);
  const needsSync = counted.some((c) => c.type !== "lead");

  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [pillars, setPillars] = useState<PillarsSnapshot | null>(null);
  const [showTopPages, setShowTopPages] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [goal, setGoal] = useState("");
  const [agree, setAgree] = useState(false);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [lockPending, startLock] = useTransition();
  const [lockError, setLockError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);

  const isFirst = versions.length === 0;
  const [open, setOpen] = useState(false);
  const formVisible = isFirst || open;

  useEffect(() => {
    setLoadError(null);
    loadBaselineAction(clientId, events, "", acknowledged).then((result) => {
      if (result.ok) setAnalysis(result.analysis);
      else setLoadError(result.error);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, acknowledged.join("|")]);

  useEffect(() => {
    loadBaselinePillarsAction(clientId, events).then((res) => {
      if (res.ok) setPillars(res.pillars);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

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

  const openBlockers = analysis?.flags.filter((f) => f.level === "blocker" && !f.acknowledged) ?? [];

  const channelMap = new Map((pillars?.traffic.channels ?? []).map((c) => [c.channel, c]));
  const directCh = channelMap.get("direct_unattributed");
  const aiRefCh = channelMap.get("ai_referral");
  const otherChannels = (pillars?.traffic.channels ?? []).filter(
    (c) => c.channel !== "organic_search" && c.channel !== "direct_unattributed" && c.channel !== "ai_referral",
  );

  const prereqs = pillars
    ? [
        {
          label: "GA4 & Search Console synced",
          ok: pillars.traffic.total_sessions.total_90d > 0 && pillars.visibility.gsc.impressions.total_90d > 0,
          href: `/${slug}/settings/connections`,
        },
        {
          label: "Watchlist configured",
          ok: pillars.visibility.watchlist.tracked_keywords > 0,
          href: `/${slug}/settings/watchlist`,
        },
        {
          label: "LLM visibility run completed",
          ok: pillars.visibility.llm.run_date != null,
          href: `/${slug}/llm`,
        },
        {
          label: "Site & GEO health crawled",
          ok: pillars.visibility.site_health.crawl_date != null,
          href: `/${slug}/site-health`,
        },
        {
          label: "Conversions configured",
          ok: counted.length > 0,
          href: `/${slug}/settings/conversions`,
        },
      ]
    : [];
  const missingPrereqs = prereqs.filter((p) => !p.ok);

  return (
    <div className="space-y-6">
      {/* Setup Readiness Check */}
      {pillars ? (
        <div
          className={`rounded-xl border p-4 text-xs ${
            missingPrereqs.length > 0 ? "border-amber-200 bg-amber-50/70" : "border-[var(--border)] bg-[var(--surface)]"
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-semibold text-[var(--text-primary)]">
              {missingPrereqs.length > 0
                ? "Complete setup before locking your baseline"
                : "All setup prerequisites ready for baseline capture"}
            </span>
            <span className="text-[var(--text-tertiary)]">
              Recommended order: Connections → Conversions → Watchlist → Competitors → LLM Run → Baseline
            </span>
          </div>
          <div className="mt-2.5 flex flex-wrap gap-2">
            {prereqs.map((p) => (
              <Link
                key={p.label}
                href={p.href}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-medium ${
                  p.ok
                    ? "border-green-200 bg-green-50 text-green-800"
                    : "border-amber-300 bg-white text-amber-900 hover:bg-amber-50"
                }`}
              >
                <span aria-hidden="true">{p.ok ? "✓" : "!"}</span>
                <span>{p.label}</span>
              </Link>
            ))}
          </div>
        </div>
      ) : null}

      {/* Unified Baseline Funnel: Visibility -> Traffic -> Conversions */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Starting Baseline</h2>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              Funnel snapshot across Visibility, Traffic, and {noun.plural} (counting <strong>{events.join(", ")}</strong> from GA4).
              {pillars ? ` Window: ${pillars.window.start_90d} to ${pillars.window.as_of}.` : ""}
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
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => handleExportCsv()}
              disabled={!pillars}
              className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-xs font-semibold hover:bg-[var(--bg)] disabled:opacity-50"
            >
              Export CSV
            </button>
            {analysis && !formVisible ? (
              <button
                type="button"
                onClick={() => {
                  setLocked(false);
                  setOpen(true);
                }}
                className="rounded-lg bg-[var(--brand-dark)] px-3 py-1.5 text-xs font-semibold text-white"
              >
                New baseline
              </button>
            ) : null}
          </div>
        </div>

        {exportError ? <p role="alert" className="text-xs text-red-700">{exportError}</p> : null}
        {loadError ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{loadError}</p> : null}

        {!pillars ? (
          <p className="text-sm text-[var(--text-secondary)]">Loading starting baseline…</p>
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
                <div className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--bg)]">
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

      {/* Blockers */}
      {openBlockers.length > 0 || (analysis?.flags.some((f) => f.level === "blocker") ?? false) ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6">
          <h2 className="text-sm font-semibold text-red-800">This stops the baseline from locking</h2>
          <ul className="mt-3 space-y-2 text-sm text-red-800">
            {analysis?.flags
              .filter((flag) => flag.level === "blocker")
              .map((flag) => (
                <li key={flag.code} className="flex items-start justify-between gap-3">
                  <span>{flag.message}</span>
                  <label className="flex shrink-0 items-center gap-1.5 text-xs">
                    <input
                      type="checkbox"
                      checked={flag.acknowledged || acknowledged.includes(flag.code)}
                      onChange={(e) =>
                        setAcknowledged((current) =>
                          e.target.checked ? [...current, flag.code] : current.filter((c) => c !== flag.code),
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

      {/* Lock form */}
      {analysis && formVisible ? (
        <form
          className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6"
          onSubmit={(event) => {
            event.preventDefault();
            setLockError(null);
            setLocked(false);
            startLock(async () => {
              const result = await lockBaselineAction(clientId, slug, {
                lead_events: events,
                regime_start: null,
                acknowledged,
                reason_code: isFirst ? null : reason,
                reason_note: isFirst ? null : note.trim() || null,
                monthly_lead_goal: goal.trim() ? Number(goal) : null,
                sync_lead_conversions: agree,
              });
              if (result.ok) {
                setLocked(true);
                setOpen(false);
                setReason("");
                setNote("");
                setAgree(false);
              } else setLockError(result.error);
            });
          }}
        >
          <h2 className="text-sm font-semibold">{isFirst ? "Lock starting baseline" : "Create a new baseline"}</h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Saves the 3-pillar snapshot above as version {versions.length + 1}. Locked baselines never change.
          </p>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="font-semibold">Optional monthly {noun.singular} goal</span>
              <input
                type="number"
                min={0}
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder={currentGoal != null ? `Current: ${currentGoal}` : "Leave blank to capture data only"}
                className={`${inputClass} mt-1`}
              />
            </label>
            {!isFirst ? (
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
            ) : null}
          </div>
          {!isFirst ? (
            <label className="mt-4 block text-sm">
              <span className="font-semibold">Say why, in a sentence</span>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} required minLength={10} className={`${inputClass} mt-1`} />
            </label>
          ) : null}

          {needsSync ? (
            <label className="mt-4 flex items-start gap-2 text-sm">
              <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1" />
              <span>Update the client&apos;s lead conversions to match what this baseline counted.</span>
            </label>
          ) : null}

          <div className="mt-4">
            <SaveBar
              pending={lockPending}
              saved={locked}
              error={lockError}
              label={`Lock as version ${versions.length + 1}`}
              disabled={openBlockers.length > 0 || (needsSync && !agree)}
            />
          </div>
          {!isFirst ? (
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="mt-3 text-sm text-[var(--text-secondary)] hover:underline"
            >
              Cancel
            </button>
          ) : null}
        </form>
      ) : null}

      {/* Locked Versions */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
        <h2 className="text-sm font-semibold">Locked Versions</h2>
        {versions.length === 0 ? (
          <p className="mt-2 text-sm text-[var(--text-tertiary)]">Nothing locked yet.</p>
        ) : (
          <div className="mt-3 overflow-x-auto rounded-lg border border-[var(--border)]">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-[var(--border)] bg-[var(--bg)] text-[var(--text-secondary)]">
                <tr>
                  <th className="px-3 py-2 font-semibold">Version</th>
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
                    <td className="px-3 py-2.5 text-[var(--text-secondary)]">
                      <span className="capitalize">{v.reason_code.replace(/_/g, " ")}</span>
                      {v.reason_note ? <div className="text-[11px] text-[var(--text-tertiary)]">&ldquo;{v.reason_note}&rdquo;</div> : null}
                    </td>
                    <td className="px-3 py-2.5 text-[var(--text-secondary)]">
                      <div>
                        {fmt(v.monthly_leads)} {noun.plural}/mo · {fmt(v.monthly_sessions)} sessions/mo
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
                          className="rounded border border-[var(--border)] bg-white px-2.5 py-1 font-semibold hover:bg-[var(--bg)]"
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
        )}
      </div>
    </div>
  );
}
