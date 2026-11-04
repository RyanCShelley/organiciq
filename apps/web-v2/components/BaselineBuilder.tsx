"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import { loadBaselineAction, lockBaselineAction } from "@/app/(app)/[clientSlug]/settings/baseline/actions";
import { SaveBar, inputClass } from "@/components/ui/form";
import {
  REBASELINE_REASONS,
  conversionNoun,
  type Analysis,
  type BaselineVersion,
  type Range,
} from "@/lib/baseline";

const fmt = (n: number | null | undefined, digits = 0) =>
  n == null ? "–" : n.toLocaleString(undefined, { maximumFractionDigits: digits });

const LEVEL_STYLE: Record<string, string> = {
  blocker: "bg-red-50 text-red-800",
  warning: "bg-amber-50 text-amber-800",
  info: "bg-[var(--bg)] text-[var(--text-secondary)]",
};

function Stat({ label, value, range, suffix = "" }: { label: string; value: number; range?: Range | string; suffix?: string }) {
  const r = typeof range === "object" ? range : null;
  return (
    <div className="rounded-lg border border-[var(--border)] p-4">
      <div className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums">
        {fmt(value, suffix ? 2 : 0)}
        {suffix}
      </div>
      {r ? (
        <div className="mt-1 text-xs text-[var(--text-secondary)]">
          typically {fmt(r.low, suffix ? 2 : 0)}–{fmt(r.high, suffix ? 2 : 0)}
          {suffix}
        </div>
      ) : null}
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
  // First month to count. Empty means everything in the window; months before it are left out of the baseline.
  const [regimeStart, setRegimeStart] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, startLoading] = useTransition();

  const [goal, setGoal] = useState("");
  const [agree, setAgree] = useState(false);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [lockPending, startLock] = useTransition();
  const [lockError, setLockError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);

  const isFirst = versions.length === 0;
  // Once a baseline is locked the form stays closed: a new one is the exception, not the next step.
  const [open, setOpen] = useState(false);
  const formVisible = isFirst || open;

  useEffect(() => {
    setLoadError(null);
    startLoading(async () => {
      const result = await loadBaselineAction(clientId, events, regimeStart, acknowledged);
      if (result.ok) setAnalysis(result.analysis);
      else setLoadError(result.error);
    });
    // The event list comes from the server and does not change while this is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, acknowledged.join("|"), regimeStart]);

  const maxLeads = Math.max(1, ...(analysis?.series.map((m) => m.leads) ?? [1]));
  const openBlockers = analysis?.flags.filter((f) => f.level === "blocker" && !f.acknowledged) ?? [];
  const suggestedGoal = analysis?.projection.suggested_monthly_lead_goal ?? null;

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
        <h2 className="text-sm font-semibold">Baseline: where {noun.plural} stand today</h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Counting <strong>{events.join(", ")}</strong> from GA4 as {noun.plural}. Everything below is worked out
          from the synced data and saved only when you lock it.
          {model == null ? (
            <>
              {" "}
              This client has no business type yet, so they are called leads: set it on{" "}
              <Link href={`/${slug}/settings`} className="font-semibold text-[var(--brand-teal)] hover:underline">
                General
              </Link>
              .
            </>
          ) : null}
        </p>

        {loadError ? (
          <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">
            {loadError}
          </p>
        ) : null}
        {!analysis && loading ? <p className="mt-4 text-sm text-[var(--text-secondary)]">Working it out from GA4…</p> : null}

        {analysis ? (
          <div className={loading ? "opacity-60" : ""}>
            <div className="mt-4 grid gap-3 sm:grid-cols-4">
              <Stat label={`${noun.plural} / month`} value={analysis.baseline.monthly_leads} range={analysis.ranges.monthly_leads} />
              <Stat label="Sessions / month" value={analysis.baseline.monthly_sessions} range={analysis.ranges.monthly_sessions} />
              <Stat label="Organic sessions / month" value={analysis.baseline.monthly_organic_sessions} range={analysis.ranges.monthly_organic_sessions} />
              <Stat label="Conversion rate" value={analysis.baseline.lead_rate_pct} range={analysis.ranges.lead_rate_pct} suffix="%" />
            </div>
            <p className="mt-3 text-sm text-[var(--text-secondary)]">
              Built from {analysis.window.from} to {analysis.window.to} ({analysis.window.months} months). Goals start
              from {analysis.goal_basis.basis}: <strong>{fmt(analysis.goal_basis.monthly_leads)}</strong> {noun.plural} a
              month.
            </p>

            <div className="mt-4 rounded-lg bg-[var(--bg)] p-4">
              <label className="block text-sm">
                <span className="font-semibold">Count from</span>
                <span className="mt-1 flex flex-wrap items-center gap-3">
                  <input
                    type="month"
                    value={regimeStart}
                    min={analysis.window.from.slice(0, 7)}
                    max={analysis.window.to.slice(0, 7)}
                    onChange={(e) => {
                      setAcknowledged([]);
                      setRegimeStart(e.target.value);
                    }}
                    className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm"
                  />
                  {analysis.window.suggested_regime_start && regimeStart !== analysis.window.suggested_regime_start.slice(0, 7) ? (
                    <button
                      type="button"
                      onClick={() => {
                        setAcknowledged([]);
                        setRegimeStart(analysis.window.suggested_regime_start!.slice(0, 7));
                      }}
                      className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm font-semibold hover:bg-white/60"
                    >
                      Use {analysis.window.suggested_regime_start.slice(0, 7)} (where the numbers stepped)
                    </button>
                  ) : null}
                  {regimeStart ? (
                    <button type="button" onClick={() => { setAcknowledged([]); setRegimeStart(""); }} className="text-sm text-[var(--text-secondary)] underline">
                      Count everything
                    </button>
                  ) : null}
                </span>
                <span className="mt-1 block text-xs text-[var(--text-secondary)]">
                  {regimeStart
                    ? `Months before ${regimeStart} are left out of the baseline, for example from before a relaunch or before tracking worked. They stay in the data.`
                    : "Leave empty to count every month in the window. Set it to the first month that is comparable with today, for example after a relaunch or once tracking worked."}
                </span>
              </label>
            </div>

            {analysis.flags
              .filter((flag) => flag.level === "warning")
              .map((flag) => (
                <p key={flag.code} className="mt-2 text-sm text-amber-800">
                  Worth knowing: {flag.message}
                </p>
              ))}
          </div>
        ) : null}
      </div>

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
          <p className="mt-3 text-xs text-red-800">To move the baseline start instead, set <strong>Count from</strong> in the card above.</p>
        </div>
      ) : null}

      {analysis ? (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <h2 className="text-sm font-semibold">Checkpoints</h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Where {noun.plural} should be at each point if the plan works. The 12-month figure is the goal.
          </p>
          <table className="mt-3 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
              <tr>
                <th className="py-2 font-medium">When</th>
                <th className="px-3 py-2 text-right font-medium">Sessions</th>
                <th className="px-3 py-2 text-right font-medium">Rate</th>
                <th className="px-3 py-2 text-right font-medium">{noun.plural}</th>
              </tr>
            </thead>
            <tbody>
              {analysis.projection.checkpoints.map((c) => (
                <tr key={c.label} className={`border-t border-[var(--border)] ${c.month === analysis.projection.goal_horizon_months ? "font-semibold" : ""}`}>
                  <td className="py-2">{c.label}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(c.monthly_sessions)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(c.lead_rate_pct, 2)}%</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(c.monthly_leads)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-[var(--text-tertiary)]">{analysis.projection.disclaimer}</p>
        </div>
      ) : null}

      {analysis ? (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <h2 className="text-sm font-semibold">Month by month</h2>
          <table className="mt-3 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
              <tr>
                <th className="py-2 font-medium">Month</th>
                <th className="px-3 py-2 text-right font-medium">Sessions</th>
                <th className="px-3 py-2 text-right font-medium">Organic</th>
                <th className="px-3 py-2 text-right font-medium">{noun.plural}</th>
                <th className="w-1/3 px-3 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {[...analysis.series].reverse().map((m) => (
                <tr key={m.month} className={`border-t border-[var(--border)] ${m.in_window ? "" : "text-[var(--text-tertiary)]"}`}>
                  <td className="py-1.5">{m.month}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(m.sessions)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(m.organic_sessions)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{fmt(m.leads)}</td>
                  <td className="px-3 py-1.5">
                    <div
                      className={`h-2 rounded ${m.in_window ? "bg-[var(--brand-teal)]" : "bg-[var(--border)]"}`}
                      style={{ width: `${Math.max(2, (m.leads / maxLeads) * 100)}%` }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-[var(--text-tertiary)]">Greyed months are outside the window used for the baseline.</p>
        </div>
      ) : null}

      {analysis && !formVisible ? (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <h2 className="text-sm font-semibold">
            Version {versions[0].version} is the locked baseline
          </h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {locked ? "Locked. " : ""}You only need a new one after a site relaunch, a tracking change, or if the
            first one was wrong. The numbers above are today&apos;s, for comparison.
          </p>
          <button
            type="button"
            onClick={() => {
              setLocked(false);
              setOpen(true);
            }}
            className="mt-4 rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white"
          >
            Create new baseline
          </button>
        </div>
      ) : null}

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
                regime_start: regimeStart || null,
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
          <h2 className="text-sm font-semibold">{isFirst ? "Lock the baseline" : "Create a new baseline"}</h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Locking saves these numbers as version {versions.length + 1} and sets the {analysis.projection.goal_horizon_months}
            -month goal. A locked baseline never changes; a new one is a new version with a reason.
          </p>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="font-semibold">Monthly {noun.singular} goal ({analysis.projection.goal_horizon_months} months)</span>
              <input
                type="number"
                min={0}
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder={suggestedGoal != null ? `${suggestedGoal} (from the checkpoints)` : ""}
                className={`${inputClass} mt-1`}
              />
              <span className="mt-1 block text-xs text-[var(--text-secondary)]">
                Leave blank to use the checkpoint figure.{currentGoal != null ? ` Current goal: ${currentGoal}.` : ""}
              </span>
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
              <span>
                Count <strong>{events.join(", ")}</strong> as this client&apos;s {noun.plural} everywhere, so the dashboard,
                alerts and the engine count what the baseline counted.
              </span>
            </label>
          ) : null}

          {openBlockers.length > 0 ? (
            <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">
              Tick “I have checked this” above before locking.
            </p>
          ) : null}
          <SaveBar label={isFirst ? "Lock baseline" : "Lock new baseline"} savedLabel="Locked." pending={lockPending} saved={locked} error={lockError} disabled={openBlockers.length > 0 || (needsSync && !agree) || loading} />
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

      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
        <h2 className="text-sm font-semibold">Versions</h2>
        {versions.length === 0 ? (
          <p className="mt-2 text-sm text-[var(--text-tertiary)]">Nothing locked yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-[var(--border)] text-sm">
            {versions.map((v) => (
              <li key={v.version} className="py-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold">
                    Version {v.version} <span className="font-normal text-[var(--text-secondary)]">· {v.reason_code.replace("_", " ")}</span>
                  </span>
                  <span className="text-xs text-[var(--text-secondary)]">
                    {v.locked_at ? new Date(v.locked_at).toLocaleDateString() : ""} · {v.locked_by}
                    {v.status === "provisional" ? " · provisional" : ""}
                  </span>
                </div>
                <div className="mt-1 text-xs text-[var(--text-secondary)]">
                  {fmt(v.monthly_leads)} {noun.plural}/month, {fmt(v.monthly_sessions)} sessions/month ({v.window_from} to{" "}
                  {v.window_to}); goal base {fmt(v.goal_monthly_leads)}. Counted: {v.lead_events.join(", ")}.
                </div>
                {v.reason_note ? <div className="mt-1 text-xs text-[var(--text-tertiary)]">&ldquo;{v.reason_note}&rdquo;</div> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
