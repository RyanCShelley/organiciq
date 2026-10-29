import { cn } from "@/lib/cn";

function buildPaths(
  values: number[],
  width: number,
  height: number,
  pad = 1,
): { line: string; area: string } | null {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const usableH = height - pad * 2;
  const stepX = width / (values.length - 1);

  const points = values.map((value, index) => {
    const x = index * stepX;
    const y = pad + usableH - ((value - min) / span) * usableH;
    return { x, y };
  });

  const line = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
  const last = points[points.length - 1];
  const first = points[0];
  const area = `${line} L${last.x.toFixed(2)} ${height} L${first.x.toFixed(2)} ${height} Z`;
  return { line, area };
}

export function Sparkline({
  values,
  className,
  width = 86,
  height = 30,
  invert = false,
  direction,
  stroke,
  fill,
}: {
  values?: number[] | null;
  className?: string;
  width?: number;
  height?: number;
  /** When true (e.g. position), falling values color as positive. */
  invert?: boolean;
  /**
   * Which way the metric moved, from the same comparison the card's change
   * pill shows. The colour follows this and not the line: daily values are
   * noisy, so a period that is up can still end on a lower day than it began.
   * Left out, the colour falls back to the first and last points.
   */
  direction?: "up" | "down" | "flat";
  /** Override stroke color (e.g. lime on glass cards). */
  stroke?: string;
  fill?: string;
}) {
  const series = (values ?? []).filter((v) => typeof v === "number" && !Number.isNaN(v));
  if (series.length < 2) {
    return (
      <div
        className={cn("inline-flex items-center justify-end text-[var(--text-tertiary)]", className)}
        style={{ width, height }}
        aria-hidden
      >
        <span className="block h-px w-full bg-[var(--border)]" />
      </div>
    );
  }

  const paths = buildPaths(series, width, height);
  if (!paths) return null;

  const first = series[0];
  const last = series[series.length - 1];
  const rising = direction ? direction === "up" : last > first;
  const falling = direction ? direction === "down" : last < first;
  const positive = invert ? falling : rising;
  const negative = invert ? rising : falling;
  const autoStroke = positive
    ? "var(--success)"
    : negative
      ? "var(--danger)"
      : "var(--text-tertiary)";
  const resolvedStroke = stroke ?? autoStroke;
  const resolvedFill =
    fill ??
    (positive
      ? "rgb(0 169 157 / 14%)"
      : negative
        ? "rgb(192 57 43 / 10%)"
        : "rgb(122 131 140 / 10%)");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className={cn("shrink-0 overflow-visible", className)}
      aria-hidden
    >
      <path d={paths.area} fill={resolvedFill} stroke="none" />
      <path
        d={paths.line}
        fill="none"
        stroke={resolvedStroke}
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
