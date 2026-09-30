import Link from "next/link";

import type {
  BaselineCheckpoint,
  BaselineCumulativePoint,
  DashboardBaseline,
} from "@/lib/dashboard";

/**
 * Baseline stats and the pacing charts, as two separate cards.
 *
 * The charts are cumulative: each point is the running total since the first
 * day of the window, so the last one is the period's total and the slope is
 * the rate we are adding at. The question they answer is "are we counting
 * toward the goal", which a rate series cannot show — a flat stretch on a
 * running total is visibly lost ground.
 *
 * They follow the dashboard's date filter, like every other card, and carry
 * three series: the window, the period before it, and the frozen projection.
 * The previous period is drawn on the same x positions as the current one
 * rather than at its own dates, so the two overlay — the comparison is "this
 * window against the last one", not a continuous history.
 *
 * The projection is stored as monthly figures, so it is accumulated at a daily
 * rate across the window: the dashed line is the pace that reaches the target,
 * and it lengthens with the picked range rather than restating a month.
 *
 * Traffic is projected to *decline* (see growth_calculator), so the question
 * the projection answers is "are we above or below the pace", not "are we
 * climbing to a target". The assumption is printed under the charts so it can
 * be argued with rather than mistaken for a bug.
 *
 * The chart is inline SVG drawn from the payload — the shapes only. Every label
 * is HTML positioned over the plot in percentages derived from the same scale
 * functions, so text stays selectable, inherits the type scale, and reflows
 * with the card instead of being baked into the viewBox.
 */


const LIME = "#b6e34b";
const CYAN = "#7fd4e8";
const PREVIOUS = "#8aa0ab";
const DOWN = "#ef8b8b";
const HAIRLINE = "#33474f";
const GRIDLINE = "#354952";
const FUTURE_TICK = "#7e94a0";
const CARD_BG = "#22333d";
const CURRENT_FILL = "rgba(182, 227, 75, 0.14)";
const PREVIOUS_FILL = "rgba(138, 160, 171, 0.14)";

const VIEW_W = 520;
const VIEW_H = 250;
const PLOT = { top: 18, right: 12, bottom: 24, left: 46 };
const PLOT_W = VIEW_W - PLOT.left - PLOT.right;
const PLOT_H = VIEW_H - PLOT.top - PLOT.bottom;
const GRIDLINE_COUNT = 5;
/** Headroom above the tallest point so the line never touches the card edge. */
const Y_HEADROOM = 1.12;
const DAYS_PER_MONTH = 365 / 12;
const X_TICK_COUNT = 5;

/** x is the day's index in the window, so the two periods lie over each other. */
type Point = { x: number; value: number };

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

function shortDate(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
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
const NICE_STEPS = [1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 7.5, 8, 10];

function niceStep(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalized = value / magnitude;
  const step = NICE_STEPS.find((candidate) => normalized <= candidate) ?? 10;
  return step * magnitude;
}

/**
 * Pick the axis top by choosing the *gridline step* first, so every label is a
 * round number. Taking a nice ceiling and dividing it by four instead gives
 * fractional gridlines, which round to the likes of 0 / 8 / 15 / 23 / 30.
 */
function axisTop(peak: number): number {
  const divisions = GRIDLINE_COUNT - 1;
  if (!Number.isFinite(peak) || peak <= 0) return divisions;
  let step = niceStep((peak * Y_HEADROOM) / divisions);
  // Leads and other small counts have no meaningful fractional gridline.
  if (step < 10) step = Math.ceil(step);
  return step * divisions;
}

function daysBetween(fromIso: string, toIso: string): number | null {
  const from = new Date(`${fromIso}T00:00:00Z`).getTime();
  const to = new Date(`${toIso}T00:00:00Z`).getTime();
  if (Number.isNaN(from) || Number.isNaN(to)) return null;
  return Math.round((to - from) / 86_400_000);
}

/** Linear interpolation between frozen checkpoints — the curve is only defined at those. */
function interpolate(points: Point[], at: number): number | null {
  if (!points.length) return null;
  if (at < points[0].x || at > points[points.length - 1].x) return null;
  for (let i = 0; i < points.length - 1; i += 1) {
    const a = points[i];
    const b = points[i + 1];
    if (at >= a.x && at <= b.x) {
      if (b.x === a.x) return a.value;
      return a.value + ((b.value - a.value) * (at - a.x)) / (b.x - a.x);
    }
  }
  return points[points.length - 1].value;
}

function percentChange(current: number | null, previous: number | null): number | null {
  if (current === null || previous === null || previous === 0) return null;
  return ((current - previous) / previous) * 100;
}

function Chip({ text, color }: { text: string; color: string }) {
  return (
    <span className="text-[11.5px] font-bold" style={{ color }}>
      {text}
    </span>
  );
}

function TrailingChart({
  title,
  current,
  previous,
  projection,
  dates,
  spanDays,
  format,
}: {
  title: string;
  current: Point[];
  previous: Point[];
  projection: Point[];
  dates: string[];
  spanDays: number;
  format: (value: number) => string;
}) {
  const projectedAt = (x: number) => interpolate(projection, x);

  const peak = [current, previous, projection].reduce(
    (max, series) => series.reduce((inner, point) => Math.max(inner, point.value), max),
    0,
  );
  const yMax = axisTop(peak);

  const x = (index: number) =>
    spanDays <= 0 ? PLOT.left + PLOT_W / 2 : PLOT.left + (index / spanDays) * PLOT_W;
  const y = (value: number) => PLOT.top + PLOT_H * (1 - Math.min(value, yMax) / yMax);
  const leftPct = (index: number) => (x(index) / VIEW_W) * 100;
  const topPct = (value: number) => (y(value) / VIEW_H) * 100;

  const latest = current.length ? current[current.length - 1] : null;
  const latestPrevious = previous.length ? previous[previous.length - 1] : null;
  const change = percentChange(latest?.value ?? null, latestPrevious?.value ?? null);
  const targetNow = latest ? projectedAt(latest.x) : null;
  const gap = latest && targetNow !== null ? latest.value - targetNow : null;

  const tickIndexes =
    dates.length <= 1
      ? [0]
      : Array.from({ length: X_TICK_COUNT }, (_, i) =>
          Math.round((i / (X_TICK_COUNT - 1)) * (dates.length - 1)),
        ).filter((value, index, all) => all.indexOf(value) === index);

  const line = (points: Point[]) => points.map((p) => `${x(p.x)},${y(p.value)}`).join(" ");
  /** The line closed down to the baseline, so a running total reads as volume. */
  const area = (points: Point[]) =>
    [
      `${x(points[0].x)},${y(0)}`,
      ...points.map((p) => `${x(p.x)},${y(p.value)}`),
      `${x(points[points.length - 1].x)},${y(0)}`,
    ].join(" ");

  return (
    <div className="min-w-0">
      <div className="text-[11.5px] font-semibold text-[var(--brand-on-dark-muted)]">{title}</div>
      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <span className="font-[family-name:var(--font-display)] text-[26px] font-black leading-none tracking-[-0.02em] text-white">
          {latest ? format(latest.value) : "—"}
        </span>
        {change !== null ? (
          <Chip text={`${formatDelta(change)} vs previous`} color={change >= 0 ? LIME : DOWN} />
        ) : null}
        {gap !== null ? (
          <Chip
            text={`${format(Math.abs(gap))} ${gap >= 0 ? "ahead of" : "behind"} pace`}
            color={gap >= 0 ? LIME : DOWN}
          />
        ) : null}
      </div>

      <div className="relative mt-3">
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          style={{ width: "100%", height: "auto", display: "block" }}
          role="img"
          aria-label={`${title}: running total for this period, the period before it, and the pace that reaches the target`}
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

          {previous.length > 1 ? (
            <polygon points={area(previous)} fill={PREVIOUS_FILL} />
          ) : null}
          {current.length > 1 ? (
            <polygon points={area(current)} fill={CURRENT_FILL} />
          ) : null}

          {previous.length > 1 ? (
            <polyline
              points={line(previous)}
              fill="none"
              stroke={PREVIOUS}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ) : null}

          {projection.length > 1 ? (
            <polyline
              points={line(projection)}
              fill="none"
              stroke={CYAN}
              strokeWidth={2.5}
              strokeDasharray="7 6"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ) : null}

          {current.length > 1 ? (
            <polyline
              points={line(current)}
              fill="none"
              stroke={LIME}
              strokeWidth={2.5}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ) : null}

          {latest ? (
            <circle
              cx={x(latest.x)}
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
          {tickIndexes.map((index) => (
            <span
              key={`xlab-${index}`}
              className="absolute -translate-x-1/2 whitespace-nowrap text-[10px] tabular-nums"
              style={{ left: `${leftPct(index)}%`, color: FUTURE_TICK }}
            >
              {shortDate(dates[index])}
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

function LegendKey({ color, dashed, label }: { color: string; dashed?: boolean; label: string }) {
  return (
    <span className="flex items-center gap-2 text-[11.5px] text-[var(--brand-on-dark)]">
      <span
        className={dashed ? "inline-block h-0 w-5 border-t-2 border-dashed" : "inline-block h-0.5 w-5 rounded-full"}
        style={dashed ? { borderColor: color } : { backgroundColor: color }}
      />
      {label}
    </span>
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
  const checkpoints: BaselineCheckpoint[] = projection?.checkpoints ?? [];
  const currentRows: BaselineCumulativePoint[] = baseline.cumulative?.current ?? [];
  const previousRows: BaselineCumulativePoint[] = baseline.cumulative?.previous ?? [];
  const windowDays = baseline.cumulative?.window_days || currentRows.length;

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

  const dates = currentRows.map((row) => row.date);
  const spanDays = Math.max(dates.length - 1, 0);

  const series = (rows: BaselineCumulativePoint[], key: "sessions" | "leads"): Point[] =>
    rows.map((row, index) => ({ x: index, value: row[key] }));

  /**
   * The pace line: the monthly target read at each day, divided down to a daily
   * rate and accumulated, so it rises alongside a cumulative actual.
   *
   * Past the plan's last checkpoint the final rate is held rather than the line
   * stopping, since a pace chart that ends mid-window reads as missing data.
   * Before the baseline there is genuinely no plan, so those days are skipped.
   */
  function projectionSeries(key: "monthly_sessions" | "monthly_leads"): Point[] {
    if (!anchorIso || checkpoints.length < 2 || !dates.length) return [];
    const curve = checkpoints
      .map((checkpoint) => ({ x: checkpoint.month * DAYS_PER_MONTH, value: checkpoint[key] }))
      .sort((a, b) => a.x - b.x);
    const lastDay = curve[curve.length - 1].x;
    const points: Point[] = [];
    let running = 0;
    dates.forEach((iso, index) => {
      const fromAnchor = daysBetween(anchorIso, iso);
      if (fromAnchor === null || fromAnchor < curve[0].x) return;
      const monthly = interpolate(curve, Math.min(fromAnchor, lastDay));
      if (monthly === null) return;
      running += monthly / DAYS_PER_MONTH;
      points.push({ x: index, value: running });
    });
    return points;
  }

  const hasWindow = dates.length > 1;
  const windowLine =
    dates.length > 1 ? `${formatDate(dates[0])} – ${formatDate(dates[dates.length - 1])}` : null;
  const hasProjection = projectionSeries("monthly_leads").length > 1;
  const hasPrevious = previousRows.length > 1;

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

      {/* ── Trailing 30 days ── */}
      <section className="min-w-0 overflow-hidden rounded-2xl bg-[#22333d] p-[26px_28px] text-white">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[12px] font-bold uppercase tracking-[0.14em]" style={{ color: LIME }}>
              {windowDays > 0 ? `Last ${windowDays.toLocaleString()} days` : "Selected range"}
            </div>
            <p className="mt-2.5 max-w-[62ch] text-[15px] leading-relaxed text-[var(--brand-on-dark)]">
              Running total for the period, against the same number of days before it.
            </p>
            {windowLine ? (
              <p className="mt-3 font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--brand-on-dark-muted)]">
                {windowLine}
              </p>
            ) : null}
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-4">
            {hasWindow ? (
              <>
                <LegendKey color={LIME} label="This period" />
                {hasPrevious ? <LegendKey color={PREVIOUS} label="Previous period" /> : null}
                {hasProjection ? <LegendKey color={CYAN} dashed label="Pace to target" /> : null}
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

        {!hasWindow ? (
          <p className="mt-5 rounded-[10px] border border-white/15 bg-white/5 px-4 py-6 text-center text-[13px] text-[var(--brand-on-dark)]">
            No GA4 days in this range yet — the charts fill in as data lands.
          </p>
        ) : (
          <>
            <div className="mt-5 grid gap-x-7 gap-y-6 lg:grid-cols-2">
              <TrailingChart
                title="Sessions"
                current={series(currentRows, "sessions")}
                previous={series(previousRows, "sessions")}
                projection={projectionSeries("monthly_sessions")}
                dates={dates}
                spanDays={spanDays}
                format={wholeNumber}
              />
              <TrailingChart
                title="Leads"
                current={series(currentRows, "leads")}
                previous={series(previousRows, "leads")}
                projection={projectionSeries("monthly_leads")}
                dates={dates}
                spanDays={spanDays}
                format={wholeNumber}
              />
            </div>

            {hasProjection ? (
              <p
                className="mt-5 border-t pt-4 text-[11.5px] leading-relaxed text-[var(--brand-on-dark-muted)]"
                style={{ borderColor: HAIRLINE }}
              >
                Traffic is projected to decline over the plan; leads are projected to rise on lead
                rate, not volume. The dashed line is the pace that reaches the target over this
                range — staying above it is the goal on both charts.
              </p>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}
