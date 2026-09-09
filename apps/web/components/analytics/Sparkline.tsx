import { cn } from "@/lib/cn";

function buildPath(values: number[], width: number, height: number, pad = 1): string | null {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const usableH = height - pad * 2;
  const stepX = width / (values.length - 1);

  return values
    .map((value, index) => {
      const x = index * stepX;
      const y = pad + usableH - ((value - min) / span) * usableH;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export function Sparkline({
  values,
  className,
  width = 72,
  height = 28,
  invert = false,
}: {
  values?: number[] | null;
  className?: string;
  width?: number;
  height?: number;
  /** When true (e.g. position), falling values color as positive. */
  invert?: boolean;
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

  const path = buildPath(series, width, height);
  if (!path) return null;

  const first = series[0];
  const last = series[series.length - 1];
  const rising = last > first;
  const falling = last < first;
  const positive = invert ? falling : rising;
  const negative = invert ? rising : falling;
  const stroke = positive
    ? "var(--success)"
    : negative
      ? "var(--danger)"
      : "var(--text-tertiary)";

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className={cn("shrink-0 overflow-visible", className)}
      aria-hidden
    >
      <path d={path} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
