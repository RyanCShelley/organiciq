"use client";

import { useState } from "react";

const TEAL = "var(--brand-teal)";
const GRAY = "var(--text-tertiary)";

export type Series = { date: string; now: number; before: number };

const compact = (n: number) => (n >= 10000 ? `${Math.round(n / 1000)}k` : n.toLocaleString());

/** A nice top for the y axis: 1, 2, 5 or 10 times a power of ten above the data. */
function niceMax(max: number) {
  if (max <= 4) return 4;
  const pow = Math.pow(10, Math.floor(Math.log10(max)));
  for (const f of [1, 2, 4, 5, 10]) if (max <= f * pow) return f * pow;
  return 10 * pow;
}

/**
 * Days of the range, this period against the one before it. Marks on the baseline are entries from the change log, so a
 * movement can be tied to something that was done.
 */
export function TrendChart({ data, marks = [], label }: { data: Series[]; marks?: { date: string; text: string }[]; label: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640, H = 240, L = 44, R = 12, T = 12, B = 28;
  if (data.length < 2) return <p className="text-sm text-[var(--text-secondary)]">Not enough days to draw.</p>;
  const max = niceMax(Math.max(...data.map((d) => Math.max(d.now, d.before)), 1));
  const x = (i: number) => L + (i / (data.length - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const line = (key: "now" | "before") => data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d[key]).toFixed(1)}`).join(" ");
  const area = `${line("now")} L${x(data.length - 1).toFixed(1)},${y(0)} L${x(0)},${y(0)} Z`;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  const labelAt = [0, Math.floor(data.length / 3), Math.floor((2 * data.length) / 3), data.length - 1];
  const short = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const indexOf = new Map(data.map((d, i) => [d.date, i]));
  const h = hover != null ? data[hover] : null;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="w-full" onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const i = Math.round(((((e.clientX - r.left) / r.width) * W - L) / (W - L - R)) * (data.length - 1));
          setHover(Math.max(0, Math.min(data.length - 1, i)));
        }}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeWidth="1" />
            <text x={L - 6} y={y(t) + 3} textAnchor="end" fontSize="10" fill={GRAY}>{compact(Math.round(t))}</text>
          </g>
        ))}
        <path d={area} fill={TEAL} opacity="0.08" />
        <path d={line("before")} fill="none" stroke={GRAY} strokeWidth="1.5" strokeDasharray="4 3" />
        <path d={line("now")} fill="none" stroke={TEAL} strokeWidth="2.5" strokeLinejoin="round" />
        {labelAt.map((i) => (
          <text key={i} x={x(i)} y={H - 8} textAnchor={i === 0 ? "start" : i === data.length - 1 ? "end" : "middle"} fontSize="10" fill={GRAY}>{short(data[i].date)}</text>
        ))}
        {marks.map((m) => {
          const i = indexOf.get(m.date);
          return i == null ? null : (
            <g key={m.date + m.text}>
              <line x1={x(i)} x2={x(i)} y1={T} y2={y(0)} stroke="#b45309" strokeWidth="1" strokeDasharray="2 3" opacity="0.6" />
              <circle cx={x(i)} cy={y(0)} r="3.5" fill="#b45309"><title>{`${short(m.date)}: ${m.text}`}</title></circle>
            </g>
          );
        })}
        {hover != null ? (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={T} y2={y(0)} stroke={GRAY} strokeWidth="1" />
            <circle cx={x(hover)} cy={y(data[hover].now)} r="4" fill={TEAL} />
          </g>
        ) : null}
      </svg>
      {h ? (
        <div className="pointer-events-none absolute right-2 top-2 rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-xs shadow-sm">
          <div className="font-semibold">{short(h.date)}</div>
          <div><span className="inline-block h-2 w-2 rounded-full" style={{ background: TEAL }} /> {h.now.toLocaleString()} this period</div>
          <div><span className="inline-block h-2 w-2 rounded-full bg-[var(--text-tertiary)]" /> {h.before.toLocaleString()} before</div>
        </div>
      ) : null}
      <div className="mt-1 flex gap-4 text-xs text-[var(--text-secondary)]">
        <span><span className="mr-1 inline-block h-0.5 w-4 align-middle" style={{ background: TEAL }} />This period</span>
        <span><span className="mr-1 inline-block h-0 w-4 border-t-2 border-dashed align-middle" style={{ borderColor: GRAY }} />Period before</span>
        {marks.length > 0 ? <span><span className="mr-1 inline-block h-2 w-2 rounded-full align-middle" style={{ background: "#b45309" }} />Change log entry</span> : null}
      </div>
    </div>
  );
}

const BAND_COLORS = ["#0f766e", "#2a9d8f", "#7fc8bd", "#bfe3dd", "#e5e7eb"];

/** Share of tracked keywords in each band of the results. */
export function CoverageDonut({ bands, tracked }: { bands: { top3: number; top10: number; top20: number; top100: number; outside: number }; tracked: number }) {
  const parts = [
    { label: "Top 3", n: bands.top3 },
    { label: "Positions 4–10", n: bands.top10 },
    { label: "Positions 11–20", n: bands.top20 },
    { label: "Positions 21–100", n: bands.top100 },
    { label: "Outside top 100", n: bands.outside },
  ];
  const R = 52, C = 2 * Math.PI * R;
  let offset = 0;
  const inTop10 = bands.top3 + bands.top10;
  return (
    <div className="flex flex-wrap items-center gap-6">
      <svg viewBox="0 0 140 140" className="h-36 w-36 shrink-0" role="img" aria-label={`${inTop10} of ${tracked} tracked keywords in the top 10`}>
        <g transform="rotate(-90 70 70)">
          {parts.map((p, i) => {
            const len = tracked > 0 ? (p.n / tracked) * C : 0;
            const el = <circle key={p.label} cx="70" cy="70" r={R} fill="none" stroke={BAND_COLORS[i]} strokeWidth="16" strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-offset} />;
            offset += len;
            return el;
          })}
        </g>
        <text x="70" y="68" textAnchor="middle" fontSize="22" fontWeight="700" fill="currentColor">{tracked ? Math.round((inTop10 / tracked) * 100) : 0}%</text>
        <text x="70" y="84" textAnchor="middle" fontSize="9" fill={GRAY}>in the top 10</text>
      </svg>
      <ul className="space-y-1 text-sm">
        {parts.map((p, i) => (
          <li key={p.label} className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: BAND_COLORS[i] }} />
            <span className="w-36 text-[var(--text-secondary)]">{p.label}</span>
            <span className="font-semibold tabular-nums">{p.n}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export type WeekPoint = { week: string; value: number | null };

/**
 * One value a week. With `invert` a lower number draws higher, which is how a position reads (1 at the top).
 * Bands are periods, such as Google updates, drawn behind the line.
 */
export function WeeklyLine({
  points,
  invert = false,
  bands = [],
  marks = [],
  secondary,
  primaryLabel = "Google",
  label,
  format = (n: number) => n.toLocaleString(),
  periodLabel = "Week of",
  spanDays = 6,
}: {
  points: WeekPoint[];
  invert?: boolean;
  bands?: { begin: string; end: string | null; title: string }[];
  marks?: { date: string; text: string; type?: string }[];
  secondary?: { label: string; points: WeekPoint[]; color?: string; separateAxis?: boolean };
  primaryLabel?: string;
  label: string;
  format?: (n: number) => string;
  periodLabel?: string;
  spanDays?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const secPoints = secondary?.points ?? [];
  const axisPoints = points.length >= 2 ? points : secPoints;
  const values = points.map((p) => p.value).filter((v): v is number => v != null);
  const secValues = secPoints.map((p) => p.value).filter((v): v is number => v != null);
  if (axisPoints.length < 2 || (values.length === 0 && secValues.length === 0)) {
    return <p className="text-sm text-[var(--text-secondary)]">Not enough weeks to draw.</p>;
  }

  const hasRightAxis = Boolean(secondary?.separateAxis && values.length > 0 && secValues.length > 0);
  const W = 640, H = 200, L = 44, R = hasRightAxis ? 44 : 12, T = 12, B = 26;
  const secColor = secondary?.color ?? "#2563eb";
  const primaryPool = values.length > 0 ? (secondary && !secondary.separateAxis && secValues.length > 0 ? [...values, ...secValues] : values) : secValues;
  const lo = invert ? Math.max(1, Math.floor(Math.min(...primaryPool) - 1)) : 0;
  const hi = invert ? Math.ceil(Math.max(...primaryPool) + 1) : niceMax(Math.max(...primaryPool, 1));
  const secLo = invert ? Math.max(1, Math.floor(Math.min(...secValues) - 1)) : 0;
  const secHi = invert ? Math.ceil(Math.max(...secValues, 1) + 1) : niceMax(Math.max(...secValues, 1));

  const x = (i: number) => L + (i / (axisPoints.length - 1)) * (W - L - R);
  const y = (v: number) => (invert ? T + ((v - lo) / (hi - lo || 1)) * (H - T - B) : T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B));
  const secY = (v: number) => {
    if (!hasRightAxis) return y(v);
    return invert
      ? T + ((v - secLo) / (secHi - secLo || 1)) * (H - T - B)
      : T + (1 - (v - secLo) / (secHi - secLo || 1)) * (H - T - B);
  };

  const buildPath = (pts: WeekPoint[], yFn: (v: number) => number, indexByWeek: Map<string, number>) => {
    let acc = "";
    let prevConnected = false;
    for (const p of pts) {
      const idx = indexByWeek.get(p.week);
      if (idx == null || p.value == null) {
        prevConnected = false;
        continue;
      }
      acc += `${acc && prevConnected ? "L" : "M"}${x(idx).toFixed(1)},${yFn(p.value).toFixed(1)} `;
      prevConnected = true;
    }
    return acc;
  };

  const axisIndex = new Map(axisPoints.map((p, i) => [p.week, i]));
  const primaryByWeek = new Map(points.map((p) => [p.week, p]));
  const secByWeek = new Map(secPoints.map((p) => [p.week, p]));

  const path = values.length > 0 ? buildPath(points, y, axisIndex) : "";
  const secPath = secValues.length > 0 ? buildPath(secPoints, secY, axisIndex) : "";
  const ticks = [0, 0.5, 1].map((f) => lo + f * (hi - lo));
  const secTicks = hasRightAxis ? [0, 0.5, 1].map((f) => secLo + f * (secHi - secLo)) : [];

  const t0 = new Date(`${axisPoints[0].week}T00:00:00`).getTime();
  const tN = new Date(`${axisPoints[axisPoints.length - 1].week}T00:00:00`).getTime() + spanDays * 86400000;
  const denom = tN - t0 || 1;
  const px = (iso: string) => L + ((new Date(`${iso}T00:00:00`).getTime() - t0) / denom) * (W - L - R);
  const short = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

  const visibleMarks = marks
    .map((m) => ({ ...m, mx: px(m.date) }))
    .filter((m) => Number.isFinite(m.mx) && m.mx >= L - 8 && m.mx <= W - R + 8)
    .map((m) => ({ ...m, cx: Math.max(L, Math.min(W - R, m.mx)) }));

  const hAxis = hover != null ? axisPoints[hover] : null;
  const hPrimary = hAxis ? primaryByWeek.get(hAxis.week) ?? null : null;
  const hSecondary = hAxis ? secByWeek.get(hAxis.week) ?? null : null;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="w-full" onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const i = Math.round(((((e.clientX - r.left) / r.width) * W - L) / (W - L - R)) * (axisPoints.length - 1));
          setHover(Math.max(0, Math.min(axisPoints.length - 1, i)));
        }}>
        {bands.map((b) => {
          const x1 = Math.max(L, px(b.begin));
          const x2 = Math.min(W - R, px(b.end ?? axisPoints[axisPoints.length - 1].week));
          return x2 <= L || x1 >= W - R ? null : (
            <g key={b.title + b.begin}>
              <rect x={x1} y={T} width={Math.max(3, x2 - x1)} height={H - T - B} fill="#b45309" opacity="0.14"><title>{`${b.title} (${short(b.begin)}${b.end ? ` to ${short(b.end)}` : ", still rolling out"})`}</title></rect>
            </g>
          );
        })}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--border)" />
            <text x={L - 6} y={y(t) + 3} textAnchor="end" fontSize="10" fill={values.length === 0 && secValues.length > 0 ? secColor : GRAY}>{invert ? t.toFixed(0) : compact(Math.round(t))}</text>
          </g>
        ))}
        {secTicks.map((t) => (
          <text key={`sec-${t}`} x={W - R + 6} y={secY(t) + 3} textAnchor="start" fontSize="10" fill={secColor}>{invert ? t.toFixed(0) : compact(Math.round(t))}</text>
        ))}
        {visibleMarks.map((m) => {
          const color = m.type === "visibility_check" ? "#4f46e5" : "#b45309";
          return (
            <g key={`${m.date}-${m.text}`}>
              <line x1={m.cx} x2={m.cx} y1={T} y2={H - B} stroke={color} strokeWidth="1.25" strokeDasharray="3 3" opacity="0.75" />
              <circle cx={m.cx} cy={H - B} r="3.5" fill={color}>
                <title>{`${short(m.date)}: ${m.text}`}</title>
              </circle>
            </g>
          );
        })}
        {path ? <path d={path} fill="none" stroke={TEAL} strokeWidth="2.5" strokeLinejoin="round" /> : null}
        {secPath ? <path d={secPath} fill="none" stroke={secColor} strokeWidth="2" strokeDasharray={secondary?.separateAxis ? undefined : "5 3"} strokeLinejoin="round" /> : null}
        {points.map((p) => {
          const idx = axisIndex.get(p.week);
          return p.value != null && idx != null ? <circle key={`p-${p.week}`} cx={x(idx)} cy={y(p.value)} r={hover === idx ? 4 : 2} fill={TEAL} /> : null;
        })}
        {secPoints.map((p) => {
          const idx = axisIndex.get(p.week);
          return p.value != null && idx != null ? <circle key={`s-${p.week}`} cx={x(idx)} cy={secY(p.value)} r={hover === idx ? 3.5 : 2} fill={secColor} /> : null;
        })}
        {[0, Math.floor(axisPoints.length / 2), axisPoints.length - 1].map((i) => (
          <text key={i} x={x(i)} y={H - 8} textAnchor={i === 0 ? "start" : i === axisPoints.length - 1 ? "end" : "middle"} fontSize="10" fill={GRAY}>{short(axisPoints[i].week)}</text>
        ))}
      </svg>
      {hAxis ? (
        <div className="pointer-events-none absolute right-2 top-2 rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-xs shadow-sm">
          <div className="font-semibold">{periodLabel} {short(hAxis.week)}</div>
          {values.length > 0 ? (
            <div>
              <span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: TEAL }} />
              {secondary ? `${primaryLabel}: ` : ""}
              {hPrimary?.value == null ? "no data" : format(hPrimary.value)}
            </div>
          ) : null}
          {secondary && secValues.length > 0 ? (
            <div>
              <span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: secColor }} />
              {secondary.label}: {hSecondary?.value == null ? "no data" : format(hSecondary.value)}
            </div>
          ) : null}
        </div>
      ) : null}
      {bands.length > 0 || (secondary && secValues.length > 0) || visibleMarks.length > 0 ? (
        <div className="mt-1 flex flex-wrap gap-4 text-xs text-[var(--text-secondary)]">
          {values.length > 0 && secondary && secValues.length > 0 ? (
            <span><span className="mr-1 inline-block h-0.5 w-4 align-middle" style={{ background: TEAL }} />{primaryLabel}</span>
          ) : null}
          {secondary && secValues.length > 0 ? (
            <span>
              <span
                className={`mr-1 inline-block w-4 align-middle ${secondary.separateAxis ? "h-0.5" : "h-0 border-t-2 border-dashed"}`}
                style={secondary.separateAxis ? { background: secColor } : { borderColor: secColor }}
              />
              {secondary.label}
            </span>
          ) : null}
          {bands.length > 0 ? <span><span className="mr-1 inline-block h-2.5 w-4 align-middle" style={{ background: "#b45309", opacity: 0.3 }} />Google update rolling out</span> : null}
          {visibleMarks.length > 0 ? <span><span className="mr-1 inline-block h-2 w-2 rounded-full align-middle" style={{ background: "#4f46e5" }} />Visibility check / annotation</span> : null}
        </div>
      ) : null}
    </div>
  );
}

/** A tiny line of a term's weekly position. Better (lower) draws higher. */
export function Spark({ values }: { values: (number | null)[] }) {
  const pts = values.map((v, i) => ({ v, i })).filter((p): p is { v: number; i: number } => p.v != null);
  if (pts.length < 2) return <span className="text-xs text-[var(--text-tertiary)]">–</span>;
  const lo = Math.min(...pts.map((p) => p.v)), hi = Math.max(...pts.map((p) => p.v));
  const w = 80, h = 22;
  const x = (i: number) => (i / Math.max(1, values.length - 1)) * w;
  const y = (v: number) => 2 + ((v - lo) / (hi - lo || 1)) * (h - 4);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-5 w-20" aria-hidden>
      <path d={pts.map((p, k) => `${k ? "L" : "M"}${x(p.i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ")} fill="none" stroke={TEAL} strokeWidth="1.5" />
    </svg>
  );
}
