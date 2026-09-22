import Link from "next/link";

import type { BaselineMonthlyActual, DashboardBaseline } from "@/lib/dashboard";

/**
 * Baseline progress and the benchmark curve, in one dark card.
 *
 * The chart is inline SVG drawn from the payload — the shapes only. Every label
 * is HTML positioned over the plot in percentages derived from the same scale
 * functions, so text stays selectable, inherits the type scale, and reflows
 * with the card instead of being baked into the viewBox.
 */

const LIME = "#b6e34b";
const CYAN = "#7fd4e8";
const DOWN = "#ef8b8b";
const HAIRLINE = "#33474f";
const GRIDLINE = "#354952";
const BAR = "#5c7a33";
const FUTURE_TICK = "#7e94a0";

const VIEW_W = 1000;
const VIEW_H = 300;
const PLOT = { top: 34, right: 16, bottom: 26, left: 46 };
const PLOT_W = VIEW_W - PLOT.left - PLOT.right;
const PLOT_H = VIEW_H - PLOT.top - PLOT.bottom;
const GRIDLINE_COUNT = 5;
/** Headroom above the tallest point so labels above the curve have somewhere to sit. */
const Y_HEADROOM = 1.15;
/** Checkpoints that earn a gap card; +9 is on the curve but not in the row. */
const GAP_CARD_MONTHS = [0, 3, 6, 12];

type MonthKey = string; // YYYY-MM

function monthKeyOf(value: Date): MonthKey {
  return `${value.getUTCFullYear()}-${String(value.getUTCMonth() + 1).padStart(2, "0")}`;
}

function parseMonthKey(key: MonthKey): { year: number; month: number } | null {
  const match = /^(\d{4})-(\d{2})$/.exec(key);
  if (!match) return null;
  return { year: Number(match[1]), month: Number(match[2]) - 1 };
}

function addMonths(key: MonthKey, count: number): MonthKey {
  const parsed = parseMonthKey(key);
  if (!parsed) return key;
  return monthKeyOf(new Date(Date.UTC(parsed.year, parsed.month + count, 1)));
}

function monthsBetween(from: MonthKey, to: MonthKey): number {
  const a = parseMonthKey(from);
  const b = parseMonthKey(to);
  if (!a || !b) return 0;
  return (b.year - a.year) * 12 + (b.month - a.month);
}

function monthRange(from: MonthKey, to: MonthKey): MonthKey[] {
  const span = monthsBetween(from, to);
  if (span < 0) return [from];
  return Array.from({ length: span + 1 }, (_, i) => addMonths(from, i));
}

function monthTick(key: MonthKey): string {
  const parsed = parseMonthKey(key);
  if (!parsed) return key;
  const label = new Date(Date.UTC(parsed.year, parsed.month, 1)).toLocaleDateString("en-US", {
    month: "short",
    timeZone: "UTC",
  });
  // Year only where it changes, and marked so "Jan 27" doesn't read as a date.
  return parsed.month === 0 ? `${label} \u2019${String(parsed.year).slice(2)}` : label;
}

function monthLabel(key: MonthKey): string {
  const parsed = parseMonthKey(key);
  if (!parsed) return key;
  return new Date(Date.UTC(parsed.year, parsed.month, 1)).toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** Round the axis top to something a person would choose: 1, 2 or 5 × 10ⁿ. */
function niceCeiling(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 10;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalized = value / magnitude;
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * magnitude;
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const parsed = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

function formatDelta(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const rounded = Math.abs(value) >= 10 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${value >= 0 ? "↑" : "↓"} ${Math.abs(rounded).toLocaleString()}%`;
}

function StatCell({
  label,
  value,
  delta,
  baseline,
}: {
  label: string;
  value: string;
  delta: number | null;
  baseline: string;
}) {
  const up = delta !== null && delta >= 0;
  // Gutters belong to the 3-up row; stacked cells sit flush with the card edge.
  return (
    <div className="py-4 sm:px-5 sm:first:pl-0 sm:last:pr-0">
      <div className="text-[11.5px] font-semibold text-[var(--brand-on-dark-muted)]">{label}</div>
      <div className="mt-1.5 font-[family-name:var(--font-display)] text-[30px] font-black leading-none tracking-[-0.02em] text-white">
        {value}
      </div>
      <div className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[11.5px]">
        <span className="font-bold" style={{ color: delta === null ? FUTURE_TICK : up ? LIME : DOWN }}>
          {formatDelta(delta)}
        </span>
        <span className="text-[var(--brand-on-dark-muted)]">vs baseline {baseline}</span>
      </div>
    </div>
  );
}

export function ProgressPanel({
  baseline,
  editHref,
}: {
  baseline: DashboardBaseline;
  /** Client settings, where the baseline is set and the projection re-run. */
  editHref: string | null;
}) {
  const projection = baseline.projection;
  const checkpoints = projection?.checkpoints ?? [];
  const actuals: BaselineMonthlyActual[] = baseline.monthly_actuals ?? [];

  // A measured window reads as a range; a manual snapshot only ever has one date.
  const frozenStart = baseline.period_start;
  const frozenEnd = baseline.period_end ?? baseline.as_of;
  const frozenLine =
    frozenStart && frozenEnd && frozenStart !== frozenEnd
      ? `Snapshot frozen between ${formatDate(frozenStart)} and ${formatDate(frozenEnd)}`
      : frozenEnd
        ? `Snapshot frozen ${formatDate(frozenEnd)}`
        : null;

  const currentLeads = baseline.vs_current.leads.current;

  const todayMonth = monthKeyOf(new Date());
  const baselineMonth = (baseline.period_start ?? baseline.as_of ?? "").slice(0, 7);
  const firstActualMonth = actuals[0]?.month ?? "";

  /**
   * The curve is anchored to the baseline, not to today.
   *
   * Checkpoints are computed from the baseline's own sessions and leads, so
   * month 0 *is* the baseline month and month 12 is a year after it. Anchoring
   * them on the current month would slide the whole curve forward by however
   * long ago the baseline was taken, restating every target on a date it was
   * never calculated for, and would leave the elapsed months with no curve
   * above them — which is the comparison this chart exists to make.
   */
  const anchorCandidate = (
    projection?.baseline_as_of ??
    baseline.as_of ??
    baseline.period_end ??
    ""
  ).slice(0, 7);
  const anchorMonth = parseMonthKey(anchorCandidate) ? anchorCandidate : todayMonth;

  const actualByMonth = new Map(actuals.map((row) => [row.month, row]));

  const checkpointByOffset = new Map(checkpoints.map((c) => [c.month, c]));
  const offsets = checkpoints.map((c) => c.month).sort((a, b) => a - b);
  const lastOffset = offsets.length ? offsets[offsets.length - 1] : 0;

  /** Linear interpolation between frozen checkpoints — the curve is only defined at those. */
  function projectedAt(offset: number): number | null {
    if (!offsets.length || offset < offsets[0] || offset > lastOffset) return null;
    const exact = checkpointByOffset.get(offset);
    if (exact) return exact.monthly_leads;
    let lower = offsets[0];
    let upper = lastOffset;
    for (const candidate of offsets) {
      if (candidate <= offset) lower = candidate;
      if (candidate >= offset) {
        upper = candidate;
        break;
      }
    }
    const a = checkpointByOffset.get(lower);
    const b = checkpointByOffset.get(upper);
    if (!a || !b) return null;
    if (upper === lower) return a.monthly_leads;
    const ratio = (offset - lower) / (upper - lower);
    return a.monthly_leads + (b.monthly_leads - a.monthly_leads) * ratio;
  }

  // ── Axis: earliest of baseline/anchor/first actual → end of the curve, at least today ──
  const starts = [baselineMonth, anchorMonth, firstActualMonth].filter(
    (key) => parseMonthKey(key) !== null,
  );
  const axisStart = starts.length
    ? starts.reduce((a, b) => (monthsBetween(a, b) < 0 ? b : a))
    : addMonths(todayMonth, -3);
  const lastActualMonth = actuals.length ? actuals[actuals.length - 1].month : todayMonth;
  const ends = [addMonths(anchorMonth, lastOffset), todayMonth, lastActualMonth].filter(
    (key) => parseMonthKey(key) !== null,
  );
  const axisEnd = ends.reduce((a, b) => (monthsBetween(a, b) > 0 ? b : a));
  const months = monthRange(axisStart, axisEnd);

  const highestActual = actuals.reduce((max, row) => Math.max(max, row.leads), 0);
  const highestTarget = checkpoints.reduce((max, c) => Math.max(max, c.monthly_leads), 0);
  // Actuals count toward the ceiling too: a month that beats the plan must still fit.
  const yMax = niceCeiling(Math.max(highestActual, highestTarget) * Y_HEADROOM) || 10;

  const x = (index: number) =>
    months.length <= 1 ? PLOT.left + PLOT_W / 2 : PLOT.left + (index / (months.length - 1)) * PLOT_W;
  const y = (value: number) => PLOT.top + PLOT_H * (1 - Math.min(value, yMax) / yMax);
  const leftPct = (index: number) => (x(index) / VIEW_W) * 100;
  const topPct = (value: number) => (y(value) / VIEW_H) * 100;

  const anchorIndex = Math.max(0, monthsBetween(axisStart, anchorMonth));
  /** Where the curve says we should be right now. */
  const todayOffset = monthsBetween(anchorMonth, todayMonth);
  const targetNow = projectedAt(Math.min(Math.max(todayOffset, 0), lastOffset));
  const pastHorizon = todayOffset > lastOffset;

  const actualPoints = months
    .map((month, index) => {
      const row = actualByMonth.get(month);
      return row ? { index, month, leads: row.leads, partial: row.partial } : null;
    })
    .filter((point): point is { index: number; month: string; leads: number; partial: boolean } =>
      point !== null,
    );

  const projectionPoints = months
    .map((month, index) => {
      const value = projectedAt(monthsBetween(anchorMonth, month));
      return value === null ? null : { index, value };
    })
    .filter((point): point is { index: number; value: number } => point !== null);

  const barWidth = Math.max(4, (PLOT_W / Math.max(months.length, 1)) * 0.5);
  const latestActual = actualPoints.length ? actualPoints[actualPoints.length - 1] : null;
  const hasProjection = projectionPoints.length > 1;

  /**
   * "Today's target" is the curve read at today, not checkpoint 0 — that one is
   * the baseline month, which may be a long way behind us. The rest are the
   * frozen checkpoints, dated so it is clear which month each one lands in.
   */
  type GapCard = {
    key: string;
    label: string;
    when: string | null;
    target: number;
    rate: number | null;
  };

  const gapCards: GapCard[] = [];
  if (targetNow !== null) {
    gapCards.push({
      key: "now",
      label: pastHorizon ? "Target at plan end" : "Today's target",
      when: pastHorizon ? monthLabel(addMonths(anchorMonth, lastOffset)) : monthLabel(todayMonth),
      target: targetNow,
      rate: null,
    });
  }
  for (const offset of GAP_CARD_MONTHS) {
    const checkpoint = checkpointByOffset.get(offset);
    // A checkpoint already behind us is history; the chart still plots it.
    if (!checkpoint || offset <= todayOffset) continue;
    gapCards.push({
      key: `cp-${offset}`,
      label: checkpoint.label,
      when: monthLabel(addMonths(anchorMonth, offset)),
      target: checkpoint.monthly_leads,
      rate: checkpoint.lead_rate_pct,
    });
  }

  return (
    <section className="min-w-0 overflow-hidden rounded-2xl bg-[#22333d] text-white">
      {/* ── Baseline ── */}
      <div className="p-[26px_28px]">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="min-w-0">
            <div className="text-[12px] font-bold uppercase tracking-[0.14em]" style={{ color: LIME }}>
              Baseline
            </div>
            <p className="mt-2.5 max-w-[62ch] text-[15px] leading-relaxed text-[var(--brand-on-dark)]">
              How we&rsquo;ve progressed since we started.
            </p>
            {frozenLine ? (
              <p className="mt-3 font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--brand-on-dark-muted)]">
                {frozenLine}
              </p>
            ) : null}
          </div>
          {editHref ? (
            <Link
              href={editHref}
              className="shrink-0 rounded-[10px] border-[1.5px] border-white/35 px-[15px] py-[9px] text-[12.5px] font-semibold text-white transition-colors duration-[120ms] hover:bg-white/10"
            >
              Edit baseline
            </Link>
          ) : null}
        </div>

        {!baseline.configured ? (
          <p className="mt-5 rounded-[10px] border border-white/15 bg-white/5 px-4 py-3 text-[13px] text-[var(--brand-on-dark)]">
            No baseline snapshot yet. Set monthly sessions, leads, and lead rate in{" "}
            {editHref ? (
              <Link href={editHref} className="font-semibold underline">
                Client settings
              </Link>
            ) : (
              "Client settings"
            )}
            .
          </p>
        ) : (
          <div
            className="mt-[18px] grid grid-cols-1 divide-y sm:grid-cols-3 sm:divide-x sm:divide-y-0"
            style={{ borderColor: HAIRLINE }}
          >
            <StatCell
              label="Lead rate"
              value={
                baseline.vs_current.lead_rate.current !== null
                  ? `${baseline.vs_current.lead_rate.current.toFixed(2)}%`
                  : "—"
              }
              delta={baseline.vs_current.lead_rate.change_pct}
              baseline={baseline.lead_rate !== null ? `${baseline.lead_rate.toFixed(2)}%` : "—"}
            />
            <StatCell
              label="Monthly leads"
              value={currentLeads !== null ? Math.round(currentLeads).toLocaleString() : "—"}
              delta={baseline.vs_current.leads.change_pct}
              baseline={
                baseline.monthly_leads !== null ? baseline.monthly_leads.toLocaleString() : "—"
              }
            />
            <StatCell
              label="Monthly sessions"
              value={
                baseline.vs_current.sessions.current !== null
                  ? Math.round(baseline.vs_current.sessions.current).toLocaleString()
                  : "—"
              }
              delta={baseline.vs_current.sessions.change_pct}
              baseline={
                baseline.monthly_sessions !== null ? baseline.monthly_sessions.toLocaleString() : "—"
              }
            />
          </div>
        )}
      </div>

      <div className="h-px w-full" style={{ backgroundColor: HAIRLINE }} />

      {/* ── Benchmark ── */}
      <div className="p-[26px_28px]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[12px] font-bold uppercase tracking-[0.14em]" style={{ color: LIME }}>
              Benchmark · Projection vs actual
            </div>
            <p className="mt-2.5 text-[15px] leading-relaxed text-[var(--brand-on-dark)]">
              Monthly leads to hit at each checkpoint.
            </p>
            {projection ? (
              <p className="mt-3 font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--brand-on-dark-muted)]">
                Frozen {formatDate(projection.generated_on)} · {projection.plan_label} curve
              </p>
            ) : null}
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-4">
            {/* A key to a chart that isn't there only raises questions. */}
            {hasProjection ? (
              <>
                <span className="flex items-center gap-2 text-[11.5px] text-[var(--brand-on-dark)]">
                  <span
                    className="inline-block h-0.5 w-5 rounded-full"
                    style={{ backgroundColor: LIME }}
                  />
                  Actual
                </span>
                <span className="flex items-center gap-2 text-[11.5px] text-[var(--brand-on-dark)]">
                  <span
                    className="inline-block h-0 w-5 border-t-2 border-dashed"
                    style={{ borderColor: CYAN }}
                  />
                  Projection
                </span>
              </>
            ) : null}
            {editHref ? (
              <Link
                href={editHref}
                className="text-[12.5px] font-semibold hover:underline"
                style={{ color: LIME }}
              >
                Re-run projection
              </Link>
            ) : null}
          </div>
        </div>

        {!hasProjection ? (
          <p className="mt-5 rounded-[10px] border border-white/15 bg-white/5 px-4 py-6 text-center text-[13px] text-[var(--brand-on-dark)]">
            No projection yet. Build one from the baseline in{" "}
            {editHref ? (
              <Link href={editHref} className="font-semibold underline">
                Client settings
              </Link>
            ) : (
              "Client settings"
            )}{" "}
            to see the curve.
          </p>
        ) : (
          <>
            <div className="mt-5 w-full max-w-full overflow-x-auto">
              <div className="min-w-[560px]">
            <div className="relative">
              <svg
                viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
                style={{ width: "100%", height: "auto", display: "block" }}
                role="img"
                aria-label="Monthly leads: recorded actuals against the frozen projection curve"
              >
                {Array.from({ length: GRIDLINE_COUNT }, (_, i) => {
                  const value = (yMax / (GRIDLINE_COUNT - 1)) * i;
                  return (
                    <line
                      key={i}
                      x1={PLOT.left}
                      x2={PLOT.left + PLOT_W}
                      y1={y(value)}
                      y2={y(value)}
                      stroke={GRIDLINE}
                      strokeWidth={1}
                    />
                  );
                })}

                {actualPoints.map((point) => (
                  <rect
                    key={`bar-${point.month}`}
                    x={x(point.index) - barWidth / 2}
                    y={y(point.leads)}
                    width={barWidth}
                    height={Math.max(0, PLOT.top + PLOT_H - y(point.leads))}
                    fill={BAR}
                    opacity={point.partial ? 0.3 : 0.55}
                    rx={2}
                  />
                ))}

                {actualPoints.length > 1 ? (
                  <polyline
                    points={actualPoints.map((p) => `${x(p.index)},${y(p.leads)}`).join(" ")}
                    fill="none"
                    stroke={LIME}
                    strokeWidth={2.5}
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                ) : null}

                <polyline
                  points={projectionPoints.map((p) => `${x(p.index)},${y(p.value)}`).join(" ")}
                  fill="none"
                  stroke={CYAN}
                  strokeWidth={2.5}
                  strokeDasharray="7 6"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />

                {checkpoints.map((checkpoint) => {
                  const index = anchorIndex + checkpoint.month;
                  if (index < 0 || index >= months.length) return null;
                  return (
                    <g key={`cp-${checkpoint.month}`}>
                      <line
                        x1={x(index)}
                        x2={x(index)}
                        y1={y(checkpoint.monthly_leads)}
                        y2={PLOT.top + PLOT_H}
                        stroke={CYAN}
                        strokeWidth={1}
                        strokeDasharray="3 5"
                        opacity={0.28}
                      />
                      <circle cx={x(index)} cy={y(checkpoint.monthly_leads)} r={4.5} fill={CYAN} />
                    </g>
                  );
                })}

                {latestActual ? (
                  <circle
                    cx={x(latestActual.index)}
                    cy={y(latestActual.leads)}
                    r={5}
                    fill={LIME}
                    stroke="#22333d"
                    strokeWidth={2}
                  />
                ) : null}
              </svg>

              {/* Labels live in HTML over the plot, placed with the same scales. */}
              {Array.from({ length: GRIDLINE_COUNT }, (_, i) => {
                const value = (yMax / (GRIDLINE_COUNT - 1)) * i;
                return (
                  <span
                    key={`ylab-${i}`}
                    className="pointer-events-none absolute -translate-y-1/2 text-[10.5px] tabular-nums"
                    style={{ left: 0, top: `${topPct(value)}%`, color: FUTURE_TICK }}
                  >
                    {Math.round(value).toLocaleString()}
                  </span>
                );
              })}

              {checkpoints.map((checkpoint) => {
                const index = anchorIndex + checkpoint.month;
                if (index < 0 || index >= months.length) return null;
                return (
                  <span
                    key={`cplab-${checkpoint.month}`}
                    className="pointer-events-none absolute -translate-x-1/2 -translate-y-[150%] whitespace-nowrap text-[11px] font-bold tabular-nums"
                    style={{
                      left: `${leftPct(index)}%`,
                      top: `${topPct(checkpoint.monthly_leads)}%`,
                      color: CYAN,
                    }}
                  >
                    {Math.round(checkpoint.monthly_leads).toLocaleString()}
                  </span>
                );
              })}

              {latestActual ? (
                <span
                  className="pointer-events-none absolute translate-x-2.5 -translate-y-1/2 whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-bold tabular-nums"
                  style={{
                    left: `${leftPct(latestActual.index)}%`,
                    top: `${topPct(latestActual.leads)}%`,
                    color: LIME,
                    backgroundColor: "#22333d",
                  }}
                >
                  {latestActual.leads.toLocaleString()} actual
                  {latestActual.partial ? " · month to date" : ""}
                </span>
              ) : null}
            </div>

            <div
              className="mt-1 grid"
              style={{
                gridTemplateColumns: `repeat(${months.length}, minmax(0, 1fr))`,
                paddingLeft: `${(PLOT.left / VIEW_W) * 100}%`,
                paddingRight: `${(PLOT.right / VIEW_W) * 100}%`,
              }}
            >
              {months.map((month, index) => (
                <span
                  key={month}
                  className="text-center text-[10px] tabular-nums"
                  style={{
                    color: actualByMonth.has(month) ? LIME : FUTURE_TICK,
                    marginLeft: index === 0 ? "-50%" : undefined,
                    marginRight: index === months.length - 1 ? "-50%" : undefined,
                  }}
                >
                  {monthTick(month)}
                </span>
              ))}
            </div>
              </div>
            </div>

            {actualPoints.length === 0 ? (
              <p className="mt-3 text-[11.5px] text-[var(--brand-on-dark-muted)]">
                No recorded lead months yet — showing the projection alone.
              </p>
            ) : null}

            {gapCards.length ? (
              <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {gapCards.map((card) => {
                  const target = Math.round(card.target);
                  const met = currentLeads !== null && currentLeads >= target;
                  const gap = currentLeads !== null ? Math.round(target - currentLeads) : null;
                  return (
                    <div
                      key={card.key}
                      className="rounded-[12px] border border-white/12 bg-white/[0.06] px-4 py-3"
                    >
                      <div className="text-[11.5px] font-semibold text-[var(--brand-on-dark-muted)]">
                        {card.label}
                        {card.when ? (
                          <span className="font-normal"> · {card.when}</span>
                        ) : null}
                      </div>
                      <div className="mt-1.5 font-[family-name:var(--font-display)] text-[22px] font-black leading-none tracking-[-0.02em] text-white">
                        {target.toLocaleString()}
                        <span className="ml-1.5 text-[11.5px] font-semibold text-[var(--brand-on-dark)]">
                          leads/mo
                        </span>
                      </div>
                      <div className="mt-1.5 text-[11.5px] text-[var(--brand-on-dark-muted)]">
                        <span
                          className="font-bold"
                          style={{ color: met ? LIME : "var(--brand-on-dark)" }}
                        >
                          {gap === null ? "—" : met ? "On track" : `${gap.toLocaleString()} to go`}
                        </span>
                        {card.rate !== null ? ` · ${card.rate.toFixed(2)}% rate` : ""}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
