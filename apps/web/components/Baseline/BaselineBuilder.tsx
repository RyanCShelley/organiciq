"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";

import {
  fetchBaselineSeriesAction,
  listBaselineEventsAction,
  listBaselineVersionsAction,
  lockBaselineAction,
  setBaselineGoalAction,
  type BaselineBand,
  type BaselineEventCandidates,
  type BaselineSeriesInput,
  type BaselineSeriesResult,
  type BaselineVersionRow,
} from "@/app/(app)/baseline-actions";
import { MonthBars } from "@/components/Baseline/MonthBars";
import { Alert } from "@/components/ui/Alert";
import { FieldLabel, Input, Select } from "@/components/ui/Input";

const REASONS: Record<string, string> = {
  relaunch: "The site was relaunched or migrated",
  tracking_change: "Lead or traffic tracking changed",
  definition_change: "What counts as a lead changed",
  correction: "The earlier baseline was wrong",
};

const LEVEL_STYLE: Record<string, string> = {
  blocker: "border-[#E3B25C] bg-[#FFF8E6]",
  warning: "border-[var(--border)] bg-[#FFFCF5]",
  info: "border-[var(--border)] bg-[var(--surface-muted)]",
};

function num(value: number | null | undefined, places = 0): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: places, minimumFractionDigits: places });
}

function range(band: BaselineBand | null | undefined, places = 0, suffix = ""): string {
  return band ? `${num(band.low, places)}${suffix} to ${num(band.high, places)}${suffix}` : "—";
}

/**
 * Build, check and lock a client's baseline.
 *
 * It shows what the method did with the months it was given: which months it used
 * (teal), what it noticed (flags), how far off it is likely to be (ranges), and what
 * the goal is built from. Locking recomputes everything on the server and keeps
 * each version with the reason it was made.
 */
export function BaselineBuilder({
  clientId,
  currentGoal,
}: {
  clientId: string;
  currentGoal: number | null;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [source, setSource] = useState<"ga4" | "csv">("ga4");
  const [csvText, setCsvText] = useState("");
  const [regimeStart, setRegimeStart] = useState("");
  const [candidates, setCandidates] = useState<BaselineEventCandidates | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [result, setResult] = useState<BaselineSeriesResult | null>(null);
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const [versions, setVersions] = useState<BaselineVersionRow[]>([]);
  const [reasonCode, setReasonCode] = useState("relaunch");
  const [reasonNote, setReasonNote] = useState("");
  const [goal, setGoal] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function reload(resetSelection: boolean) {
    const [events, saved] = await Promise.all([
      listBaselineEventsAction(clientId),
      listBaselineVersionsAction(clientId),
    ]);
    if (events.ok) {
      setCandidates(events.events);
      if (resetSelection) setSelected(events.events.defaults);
    }
    if (saved.ok) setVersions(saved.versions);
  }

  useEffect(() => {
    startTransition(async () => {
      await reload(true);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  const defaults = candidates?.defaults ?? [];
  const locked = candidates?.locked ?? null;
  const lockedDiffers =
    locked !== null &&
    (locked.events.some((name) => !defaults.includes(name)) || defaults.some((name) => !locked.events.includes(name)));
  const goalInfo = candidates?.goal ?? null;
  const goalDiffers =
    goalInfo !== null && goalInfo.suggested !== null && goalInfo.current !== goalInfo.suggested;

  const input = useMemo<BaselineSeriesInput>(
    () => ({
      source,
      csvText,
      regimeStart: regimeStart || undefined,
      leadEvents: source === "ga4" ? selected : undefined,
      acknowledged,
    }),
    [source, csvText, regimeStart, selected, acknowledged],
  );

  const openBlockers = result
    ? result.flags.filter((flag) => flag.level === "blocker" && !acknowledged.includes(flag.code))
    : [];
  const first = versions.length === 0;
  const nextVersion = (versions[0]?.version ?? 0) + 1;

  function calculate(override?: Partial<BaselineSeriesInput>) {
    setError(null);
    setMessage(null);
    startTransition(async () => {
      const response = await fetchBaselineSeriesAction(clientId, { ...input, ...override });
      if (!response.ok) {
        setError(response.error);
        setResult(null);
        return;
      }
      setResult(response.result);
    });
  }

  function toggleAck(code: string) {
    setAcknowledged((current) => (current.includes(code) ? current.filter((c) => c !== code) : [...current, code]));
  }

  function lock() {
    if (!result) return;
    setError(null);
    setMessage(null);
    startTransition(async () => {
      const response = await lockBaselineAction(clientId, {
        ...input,
        reasonCode: first ? "initial" : reasonCode,
        reasonNote,
        monthlyLeadGoal: goal.trim() === "" ? null : Number(goal),
        targetLeadRatePct: null,
        syncLeadConversions: false,
      });
      if (!response.ok) {
        setError(response.error);
        return;
      }
      await reload(false);
      setMessage(
        `Locked as version ${response.locked.version.version}.` +
          (response.locked.goal_set_by_lock
            ? ` Plan-end lead goal set to ${num(response.locked.monthly_lead_goal)}.`
            : "") +
          (response.locked.lead_conversions_changed ? " Lead conversions updated to match." : ""),
      );
      setReasonNote("");
      setGoal("");
      router.refresh();
    });
  }

  return (
    <div className="space-y-4 border-t border-[var(--border)] pt-4">
      <div>
        <p className="text-sm font-medium text-[var(--text-primary)]">Baseline</p>
        <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
          Built from the last few months of the current site, not a long average: for traffic that is trending
          down, a long average sets a baseline the client cannot meet. Earlier months stay on the chart in grey.
        </p>
      </div>

      {lockedDiffers && locked ? (
        <Alert variant="warning">
          <p className="text-sm">
            Baseline v{locked.version} counted <strong>{locked.events.join(", ")}</strong> as leads, but the home
            screen, alerts and results count <strong>{defaults.join(", ") || "nothing"}</strong>, so their numbers
            will not match the baseline.
          </p>
          <p className="mt-2 text-xs">This historical snapshot stays unchanged. New calculations use the saved lead definitions above.</p>
        </Alert>
      ) : null}
      {goalDiffers && goalInfo ? (
        <Alert variant="warning">
          <p className="text-sm">
            The plan-end goal is <strong>{num(goalInfo.current)}</strong> a month, but baseline v{goalInfo.version}
            &apos;s 12-month figure is <strong>{num(goalInfo.suggested)}</strong>. The home screen shows both.
          </p>
          <button
            type="button"
            className="btn btn-secondary mt-2"
            disabled={pending}
            onClick={() =>
              startTransition(async () => {
                const done = await setBaselineGoalAction(clientId, goalInfo.suggested!);
                if (!done.ok) return setError(done.error);
                setMessage(`Plan-end goal set to ${num(goalInfo.suggested)}.`);
                await reload(false);
                router.refresh();
              })
            }
          >
            Set the goal to {num(goalInfo.suggested)}
          </button>
        </Alert>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <FieldLabel label="Data from">
          <Select value={source} onChange={(event) => setSource(event.target.value as "ga4" | "csv")}>
            <option value="ga4">Synced GA4</option>
            <option value="csv">Pasted monthly CSV</option>
          </Select>
        </FieldLabel>
        <FieldLabel label="Baseline starts in (first month of the current site or tracking)">
          <Input type="month" value={regimeStart} onChange={(event) => setRegimeStart(event.target.value)} />
        </FieldLabel>
      </div>

      {source === "ga4" ? (
        <div className="rounded-lg bg-[var(--surface-muted)] p-3 text-sm">
          <p className="font-semibold">Saved lead events</p>
          <p className="mt-1">{candidates === null ? "Loading saved definitions…" : defaults.length ? defaults.join(", ") : "No lead events selected. Save lead definitions above before calculating."}</p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">This calculator counts lead events. A visit-based conversion-rate target is separate. Change lead events in Conversions, then calculate again. Locked baseline versions are preserved.</p>
        </div>
      ) : (
        <FieldLabel label="Monthly CSV (month, sessions, leads; optional organic_sessions)">
          <textarea
            value={csvText}
            onChange={(event) => setCsvText(event.target.value)}
            rows={6}
            placeholder={"month,sessions,organic_sessions,leads\n2026-07,2706,380,27\n2026-08,2928,332,8"}
            className="w-full rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2 font-[family-name:var(--font-mono)] text-xs"
          />
        </FieldLabel>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn btn-secondary" disabled={pending} onClick={() => calculate()}>
          {pending && !result ? "Calculating…" : result ? "Recalculate" : "Calculate"}
        </button>
        {result?.window.suggested_regime_start && regimeStart !== result.window.suggested_regime_start ? (
          <button
            type="button"
            className="text-sm font-semibold text-[var(--brand-teal-hover)] underline"
            onClick={() => {
              setRegimeStart(result.window.suggested_regime_start!);
              calculate({ regimeStart: result.window.suggested_regime_start! });
            }}
          >
            Start from {result.window.suggested_regime_start}, where traffic stepped
          </button>
        ) : null}
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}

      {result ? (
        <div className="space-y-4 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm">
              <span className="font-semibold">
                {result.window.from} to {result.window.to}
              </span>{" "}
              <span className="text-[var(--text-secondary)]">
                ({result.window.months} month{result.window.months === 1 ? "" : "s"})
              </span>
            </p>
            {result.status === "provisional" ? (
              <span className="rounded-full bg-[#FDF1E3] px-2.5 py-0.5 text-xs font-semibold text-[#8A4B08]">
                Provisional
              </span>
            ) : null}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <MonthBars rows={result.series} value={(row) => row.sessions} label="Sessions per month" />
            <MonthBars rows={result.series} value={(row) => row.leads} label="Leads per month" />
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-left text-xs text-[var(--text-tertiary)]">
                  <th className="py-1.5 pr-2 font-semibold">Baseline</th>
                  <th className="py-1.5 pr-2 font-semibold">Estimate</th>
                  <th className="py-1.5 font-semibold">Typical range</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-[var(--border)]">
                  <td className="py-1.5 pr-2">Sessions a month</td>
                  <td className="py-1.5 pr-2 font-medium">{num(result.baseline.monthly_sessions)}</td>
                  <td className="py-1.5">{range(result.ranges.monthly_sessions)}</td>
                </tr>
                {result.baseline.monthly_organic_sessions != null ? (
                  <tr className="border-b border-[var(--border)]">
                    <td className="py-1.5 pr-2">Organic Search sessions</td>
                    <td className="py-1.5 pr-2 font-medium">{num(result.baseline.monthly_organic_sessions)}</td>
                    <td className="py-1.5">{range(result.ranges.monthly_organic_sessions)}</td>
                  </tr>
                ) : null}
                <tr className="border-b border-[var(--border)]">
                  <td className="py-1.5 pr-2">Lead rate</td>
                  <td className="py-1.5 pr-2 font-medium">{num(result.baseline.lead_rate_pct, 2)}%</td>
                  <td className="py-1.5">{range(result.ranges.lead_rate_pct, 2, "%")}</td>
                </tr>
                <tr className="border-b border-[var(--border)]">
                  <td className="py-1.5 pr-2">Leads a month</td>
                  <td className="py-1.5 pr-2 font-medium">{num(result.baseline.monthly_leads, 1)}</td>
                  <td className="py-1.5">{range(result.ranges.monthly_leads, 1)}</td>
                </tr>
              </tbody>
            </table>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              Ranges are the typical miss in backtests, not a guarantee. Estimates have run 10 to 25% high, so the
              goal is built from the <strong>low end</strong>: {num(result.goal_basis.monthly_leads, 1)} leads a month.
            </p>
          </div>

          {result.flags.length > 0 ? (
            <ul className="space-y-2">
              {result.flags.map((flag) => (
                <li
                  key={flag.code}
                  className={`rounded-[var(--radius-md)] border px-3 py-2 text-sm ${LEVEL_STYLE[flag.level]}`}
                >
                  <p className="text-[13px] leading-snug">
                    {flag.level === "blocker" ? (
                      <span className="mr-2 rounded-full bg-[#F5D58A] px-2 py-0.5 text-[11px] font-semibold text-[#6B4A00]">
                        Check before locking
                      </span>
                    ) : null}
                    {flag.message}
                  </p>
                  {flag.level === "blocker" ? (
                    <label className="mt-1.5 flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={acknowledged.includes(flag.code)}
                        onChange={() => toggleAck(flag.code)}
                      />
                      I have checked this and want to lock anyway
                    </label>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}

          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]">
              {result.projection.plan_label} projection, from the goal basis
            </p>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              Two columns, one growth curve, two starting points. <strong>Goal</strong> starts from the
              low end of the baseline&rsquo;s lead range, so it is a number we can promise the client even if
              the baseline reads low. <strong>Estimate</strong> starts from the middle of the range, the
              likeliest outcome. The gap is widest when the baseline is only a few leads a month. Use the goal
              column for what the client is committed to; use the estimate for internal forecasting. To set
              something in between, type it as the plan-end goal when you lock.
            </p>
            <table className="mt-2 w-full min-w-[420px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-left text-xs text-[var(--text-tertiary)]">
                  <th className="py-1.5 pr-2 font-semibold">Checkpoint</th>
                  <th className="py-1.5 pr-2 font-semibold">Lead rate</th>
                  <th className="py-1.5 pr-2 font-semibold">Goal (leads a month)</th>
                  <th className="py-1.5 font-semibold">Estimate (leads a month)</th>
                </tr>
              </thead>
              <tbody>
                {result.projection.checkpoints.map((row, index) => (
                  <tr key={row.month} className="border-b border-[var(--border)]">
                    <td className="py-1.5 pr-2">{row.label}</td>
                    <td className="py-1.5 pr-2">{num(row.lead_rate_pct, 2)}%</td>
                    <td className="py-1.5 pr-2 font-medium">{num(row.monthly_leads)}</td>
                    <td className="py-1.5 text-[var(--text-secondary)]">
                      {num(result.projection_point.checkpoints[index]?.monthly_leads)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              Suggested 12-month goal: {num(result.projection.suggested_monthly_lead_goal)} leads a month.
            </p>
          </div>

          <div className="space-y-3 border-t border-[var(--border)] pt-3">
            <p className="text-sm font-medium">{first ? "Lock the first baseline" : `Lock as version ${nextVersion}`}</p>
            {first ? null : (
              <div className="grid gap-3 sm:grid-cols-2">
                <FieldLabel label="Why a new baseline">
                  <Select value={reasonCode} onChange={(event) => setReasonCode(event.target.value)}>
                    {Object.entries(REASONS).map(([code, label]) => (
                      <option key={code} value={code}>
                        {label}
                      </option>
                    ))}
                  </Select>
                </FieldLabel>
                <FieldLabel label="In a sentence (required)">
                  <Input value={reasonNote} onChange={(event) => setReasonNote(event.target.value)} />
                </FieldLabel>
              </div>
            )}
            <FieldLabel label="Plan-end monthly lead goal (optional)">
              <Input
                type="number"
                min={0}
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                placeholder={`Leave blank to use ${num(result.projection.suggested_monthly_lead_goal)}, this baseline's 12-month figure${
                  currentGoal != null ? ` (now ${num(currentGoal)})` : ""
                }`}
              />
            </FieldLabel>

            <button
              type="button"
              className="btn btn-primary"
              disabled={pending || openBlockers.length > 0}
              onClick={lock}
            >
              {pending ? "Locking…" : `Lock baseline v${nextVersion}`}
            </button>
            {openBlockers.length > 0 ? (
              <p className="text-xs text-[var(--text-secondary)]">
                {openBlockers.length} thing{openBlockers.length === 1 ? "" : "s"} to check above before this can be locked.
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      {versions.length > 0 ? (
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]">
            Locked baselines
          </p>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-left text-xs text-[var(--text-tertiary)]">
                  <th className="py-1.5 pr-2 font-semibold">Version</th>
                  <th className="py-1.5 pr-2 font-semibold">Locked</th>
                  <th className="py-1.5 pr-2 font-semibold">Why</th>
                  <th className="py-1.5 pr-2 font-semibold">Months</th>
                  <th className="py-1.5 pr-2 font-semibold">Sessions</th>
                  <th className="py-1.5 pr-2 font-semibold">Lead rate</th>
                  <th className="py-1.5 font-semibold">Leads</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((version) => (
                  <tr key={version.version} className="border-b border-[var(--border)] align-top">
                    <td className="py-1.5 pr-2 font-medium">
                      v{version.version}
                      {version.status === "provisional" ? (
                        <span className="ml-1.5 text-xs text-[#8A4B08]">provisional</span>
                      ) : null}
                    </td>
                    <td className="py-1.5 pr-2 text-xs text-[var(--text-secondary)]">
                      {version.locked_at?.slice(0, 10)}
                      <br />
                      {version.locked_by}
                    </td>
                    <td className="py-1.5 pr-2 text-xs">
                      {REASONS[version.reason_code] ?? "First baseline"}
                      {version.reason_note ? <span className="block text-[var(--text-secondary)]">{version.reason_note}</span> : null}
                    </td>
                    <td className="py-1.5 pr-2 text-xs">
                      {version.window_from} to {version.window_to}
                    </td>
                    <td className="py-1.5 pr-2">{num(version.monthly_sessions)}</td>
                    <td className="py-1.5 pr-2">{num(version.lead_rate_pct, 2)}%</td>
                    <td className="py-1.5">{num(version.monthly_leads, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
