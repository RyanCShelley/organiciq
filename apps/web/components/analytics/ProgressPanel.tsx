import Link from "next/link";

import type {
  BaselineCheckpoint,
  BaselineTrailingActual,
  DashboardBaseline,
} from "@/lib/dashboard";

/**
 * Baseline stats and the projection charts, as two separate cards.
 *
 * The charts plot a trailing 30-day window rather than calendar months: every
 * point is then directly comparable to a monthly projection figure, the line
 * has daily resolution without resetting on the 1st, and the shape of a change
 * is legible — a cliff is an event, a slope is a trend.
 *
 * Traffic is projected to *decline* (see growth_calculator), so the question
 * these charts answer is "are we above or below the line", not "are we climbing
 * to a target". The gap is shaded for that reason, and the assumption is
 * printed under the charts so it can be argued with rather than mistaken for a
 * bug.
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
const FUTURE_TICK = "#7e94a0";
const CARD_BG = "#22333d";
const BELOW_FILL = "rgba(239, 139, 139, 0.20)";
const ABOVE_FILL = "rgba(182, 227, 75, 0.18)";

const VIEW_W = 520;
const VIEW_H = 250;
const PLOT = { top: 18, right: 12, bottom: 24, left: 46 };
const PLOT_W = VIEW_W - PLOT.left - PLOT.right;
const PLOT_H = VIEW_H - PLOT.top - PLOT.bottom;
const GRIDLINE_COUNT = 5;
/** Headroom above the tallest point so the line never touches the card edge. */
const Y_HEADROOM = 1.12;
const DAYS_PER_MONTH = 365 / 12;
/** Checkpoints that earn a gap card; +9 is on the curve but not in the row. */
const GAP_CARD_MONTHS = [0, 3, 6, 12];

type Point = { day: number; value: number };
type Metric = "monthly_sessions" | "monthly_leads";

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

/**
 * Round the axis top to something a person would choose.
 *
 * The steps are finer than the usual 1/2/5 because two charts sit side by side
 * in a short card: jumping a 3,419 peak all the way to 5,000 would spend a
 * third of the plot height on empty space.
 */
const NICE_STEPS = [1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10];

function niceCeiling(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 10;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalized = value / magnitude;
  const step = NICE_STEPS.find((candidate) => normalized <= candidate) ?? 10;
  return step * magnitude;
}

function daysBetween(fromIso: string, toIso: string): number | null {
  const from = new Date(`${fromIso}T00:00:00Z`).getTime();
  const to = new Date(`${toIso}T00:00:00Z`).getTime();
  if (Number.isNaN(from) || Number.isNaN(to)) return null;
  return Math.round((to - from) / 86_400_000);
}

/**
 * Month name, carrying the year once the axis crosses out of the baseline year.
 *
 * A 12-month plan starts and ends in the same month, so without this both ends
 * of the axis read "Sep". January is rarely a checkpoint, so the year cannot
 * simply be hung on it.
 */
function monthTickLabel(anchorIso: string, day: number, baselineYear: number): string {
  const anchor = new Date(`${anchorIso}T00:00:00Z`);
  if (Number.isNaN(anchor.getTime())) return "";
  anchor.setUTCDate(anchor.getUTCDate() + Math.round(day));
  const label = anchor.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" });
  return anchor.getUTCFullYear() === baselineYear
    ? label
    : `${label} ’${String(anchor.getUTCFullYear()).slice(2)}`;
}

/** Linear interpolation between frozen checkpoints — the curve is only defined at those. */
function interpolate(points: Point[], day: number): number | null {
  if (!points.length) return null;
  if (day < points[0].day || day > points[points.length - 1].day) return null;
  for (let i = 0; i < points.length - 1; i += 1) {
    const a = points[i];
    const b = points[i + 1];
    if (day >= a.day && day <= b.day) {
      if (b.day === a.day) return a.value;
      return a.value + ((b.value - a.value) * (day - a.day)) / (b.day - a.day);
    }
  }
  return points[points.length - 1].value;
}

/**
 * Split the elapsed days into runs that sit wholly above or wholly below the
 * projection, so the gap can be shaded green or red per run rather than the
 * whole span taking its colour from the latest point.
 */
type Band = { above: boolean; actual: Point[]; projected: Point[] };

function signedBands(actual: Point[], projectionAt: (day: number) => number | null): Band[] {
  const bands: Band[] = [];
  let current: Band | null = null;
  for (const point of actual) {
    const projected = projectionAt(point.day);
    if (projected === null) {
      current = null;
      continue;
    }
    const above = point.value >= projected;
    if (!current || current.above !== above) {
      // Carry the previous point into the new band so the fill has no gap.
      const previous: Point | null =
        current && current.actual.length ? current.actual[current.actual.length - 1] : null;
      const next: Band = { above, actual: [], projected: [] };
      if (previous) {
        next.actual.push(previous);
        next.projected.push({
          day: previous.day,
          value: projectionAt(previous.day) ?? previous.value,
        });
      }
      current = next;
      bands.push(next);
    }
    current.actual.push(point);
    current.projected.push({ day: point.day, value: projected });
  }
  return bands.filter((band) => band.actual.length > 1);
}

function TrailingChart({
  title,
  anchorIso,
  actual,
  checkpoints,
  metric,
  maxDay,
  format,
}: {
  title: string;
  anchorIso: string;
  actual: Point[];
  checkpoints: BaselineCheckpoint[];
  metric: Metric;
  maxDay: number;
  format: (value: number) => string;
}) {
  const projectionPoints: Point[] = checkpoints
    .map((checkpoint) => ({
      day: checkpoint.month * DAYS_PER_MONTH,
      value: checkpoint[metric],
    }))
    .sort((a, b) => a.day - b.day);

  const projectionAt = (day: number) => interpolate(projectionPoints, day);

  const highestActual = actual.reduce((max, point) => Math.max(max, point.value), 0);
  const highestProjected = projectionPoints.reduce((max, point) => Math.max(max, point.value), 0);
  const yMax = niceCeiling(Math.max(highestActual, highestProjected) * Y_HEADROOM) || 10;

  const x = (day: number) => PLOT.left + (Math.min(day, maxDay) / maxDay) * PLOT_W;
  const y = (value: number) => PLOT.top + PLOT_H * (1 - Math.min(value, yMax) / yMax);
  const leftPct = (day: number) => (x(day) / VIEW_W) * 100;
  const topPct = (value: number) => (y(value) / VIEW_H) * 100;

  const latest = actual.length ? actual[actual.length - 1] : null;
  const targetNow = latest ? projectionAt(latest.day) : null;
  const gap = latest && targetNow !== null ? latest.value - targetNow : null;
  const bands = signedBands(actual, projectionAt);
  const tickDays = checkpoints
    .map((checkpoint) => checkpoint.month * DAYS_PER_MONTH)
    .filter((day) => day <= maxDay)
    .sort((a, b) => a - b);
  const anchorYear = new Date(`${anchorIso}T00:00:00Z`).getUTCFullYear();

  return (
    <div className="min-w-0">
      <div className="text-[11.5px] font-semibold text-[var(--brand-on-dark-muted)]">{title}</div>
      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
        <span className="font-[family-name:var(--font-display)] text-[26px] font-black leading-none tracking-[-0.02em] text-white">
          {latest ? format(latest.value) : "—"}
        </span>
        {gap !== null ? (
          <span
            className="text-[11.5px] font-bold"
            style={{ color: gap >= 0 ? LIME : DOWN }}
          >
            {format(Math.abs(gap))} {gap >= 0 ? "above" : "below"} projection
          </span>
        ) : null}
      </div>

      <div className="relative mt-3">
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          style={{ width: "100%", height: "auto", display: "block" }}
          role="img"
          aria-label={`${title}: trailing 30-day actual against the frozen projection`}
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

          {/* The gap, shaded by which side of the projection we are on. */}
          {bands.map((band, index) => (
            <polygon
              key={`band-${index}`}
              points={[
                ...band.actual.map((p) => `${x(p.day)},${y(p.value)}`),
                ...[...band.projected].reverse().map((p) => `${x(p.day)},${y(p.value)}`),
              ].join(" ")}
              fill={band.above ? ABOVE_FILL : BELOW_FILL}
            />
          ))}

          {projectionPoints.length > 1 ? (
            <polyline
              points={projectionPoints.map((p) => `${x(p.day)},${y(p.value)}`).join(" ")}
              fill="none"
              stroke={CYAN}
              strokeWidth={2.5}
              strokeDasharray="7 6"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ) : null}

          {actual.length > 1 ? (
            <polyline
              points={actual.map((p) => `${x(p.day)},${y(p.value)}`).join(" ")}
              fill="none"
              stroke={LIME}
              strokeWidth={2.5}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ) : null}

          {latest ? (
            <circle
              cx={x(latest.day)}
              cy={y(latest.value)}
              r={5}
              fill={LIME}
              stroke={CARD_BG}
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
              {format(value)}
            </span>
          );
        })}

        <div className="pointer-events-none absolute inset-x-0 bottom-0">
          {tickDays.map((day) => (
            <span
              key={`xlab-${day}`}
              className="absolute -translate-x-1/2 text-[10px] tabular-nums"
              style={{ left: `${leftPct(day)}%`, color: FUTURE_TICK }}
            >
              {monthTickLabel(anchorIso, day, anchorYear)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
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
  const trailing: BaselineTrailingActual[] = baseline.trailing_actuals ?? [];

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

  /**
   * The curve is anchored to the baseline, not to today.
   *
   * Checkpoints are computed from the baseline's own sessions and leads, so
   * month 0 *is* the baseline and month 12 is a year after it. Anchoring them
   * on today would slide the whole curve forward by however long ago the
   * baseline was taken, restating every target on a date it was never
   * calculated for.
   */
  const anchorIso = projection?.baseline_as_of ?? baseline.period_end ?? baseline.as_of ?? null;

  const lastOffsetMonths = checkpoints.reduce((max, c) => Math.max(max, c.month), 0);
  const maxDay = Math.max(lastOffsetMonths * DAYS_PER_MONTH, 1);

  const actualPoints: Point[] = anchorIso
    ? trailing
        .map((row) => {
          const day = daysBetween(anchorIso, row.date);
          return day === null || day < 0 || day > maxDay ? null : { row, day };
        })
        .filter((entry): entry is { row: BaselineTrailingActual; day: number } => entry !== null)
        .map(({ row, day }) => ({ day, value: row.sessions }))
    : [];

  const leadPoints: Point[] = anchorIso
    ? trailing
        .map((row) => {
          const day = daysBetween(anchorIso, row.date);
          return day === null || day < 0 || day > maxDay ? null : { row, day };
        })
        .filter((entry): entry is { row: BaselineTrailingActual; day: number } => entry !== null)
        .map(({ row, day }) => ({ day, value: row.leads }))
    : [];

  const hasProjection = checkpoints.length > 1 && anchorIso !== null;
  const hasTrailing = actualPoints.length > 0 || leadPoints.length > 0;

  const checkpointByOffset = new Map(checkpoints.map((c) => [c.month, c]));
  const latestDay = actualPoints.length ? actualPoints[actualPoints.length - 1].day : null;
  const todayOffsetMonths = latestDay === null ? 0 : latestDay / DAYS_PER_MONTH;

  const leadCurve: Point[] = checkpoints
    .map((c) => ({ day: c.month * DAYS_PER_MONTH, value: c.monthly_leads }))
    .sort((a, b) => a.day - b.day);
  const targetNow =
    latestDay === null ? null : interpolate(leadCurve, Math.min(latestDay, maxDay));

  type GapCard = {
    key: string;
    label: string;
    when: string | null;
    target: number;
    rate: number | null;
  };

  const gapCards: GapCard[] = [];
  if (targetNow !== null) {
    gapCards.push({ key: "now", label: "Today's target", when: null, target: targetNow, rate: null });
  }
  for (const offset of GAP_CARD_MONTHS) {
    const checkpoint = checkpointByOffset.get(offset);
    // A checkpoint already behind us is history; the chart still plots it.
    if (!checkpoint || offset <= todayOffsetMonths) continue;
    gapCards.push({
      key: `cp-${offset}`,
      label: checkpoint.label,
      when: null,
      target: checkpoint.monthly_leads,
      rate: checkpoint.lead_rate_pct,
    });
  }

  const wholeNumber = (value: number) => Math.round(value).toLocaleString();

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {/* ── Baseline ── */}
      <section className="min-w-0 overflow-hidden rounded-2xl bg-[#22333d] p-[26px_28px] text-white">
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
                {projection ? ` · ${projection.plan_label} curve` : ""}
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
      </section>

      {/* ── Trailing 30 days vs projection ── */}
      <section className="min-w-0 overflow-hidden rounded-2xl bg-[#22333d] p-[26px_28px] text-white">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[12px] font-bold uppercase tracking-[0.14em]" style={{ color: LIME }}>
              Trailing 30 days vs projection
            </div>
            <p className="mt-2.5 max-w-[62ch] text-[15px] leading-relaxed text-[var(--brand-on-dark)]">
              Each point is the last 30 days ending that day, against the projected monthly figure.
            </p>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-4">
            {hasProjection && hasTrailing ? (
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
        ) : !hasTrailing ? (
          <p className="mt-5 rounded-[10px] border border-white/15 bg-white/5 px-4 py-6 text-center text-[13px] text-[var(--brand-on-dark)]">
            No recorded days since the baseline yet — the charts fill in as GA4 data lands.
          </p>
        ) : (
          <>
            <div className="mt-5 grid gap-x-7 gap-y-6 lg:grid-cols-2">
              <TrailingChart
                title="Sessions"
                anchorIso={anchorIso as string}
                actual={actualPoints}
                checkpoints={checkpoints}
                metric="monthly_sessions"
                maxDay={maxDay}
                format={wholeNumber}
              />
              <TrailingChart
                title="Leads"
                anchorIso={anchorIso as string}
                actual={leadPoints}
                checkpoints={checkpoints}
                metric="monthly_leads"
                maxDay={maxDay}
                format={wholeNumber}
              />
            </div>

            <p className="mt-5 border-t pt-4 text-[11.5px] leading-relaxed text-[var(--brand-on-dark-muted)]"
              style={{ borderColor: HAIRLINE }}
            >
              Traffic is projected to decline over the plan; leads are projected to rise on lead
              rate, not volume. Sitting above the dashed line is the goal on both charts.
            </p>

            {gapCards.length ? (
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
      </section>
    </div>
  );
}
