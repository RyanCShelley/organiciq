import { apiFetch } from "@/lib/api";

type Source = { key: string; label: string; through: string | null; age_days: number | null; overdue: boolean };

const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** The newest data each source holds, so a stale pull is visible before anyone reads a list built on it. */
export async function DataFreshness({ clientId }: { clientId: string }) {
  const sources = await apiFetch<Source[]>("/v2/engine/freshness", { clientId }).catch(() => null);
  if (!sources) return null;
  return (
    <p className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--text-secondary)]">
      <span className="font-semibold">Data through</span>
      {sources.map((s) => (
        <span key={s.key} className={s.overdue ? "font-semibold text-red-700" : undefined}>
          {s.label} {s.through ? shortDate(s.through) : "none yet"}
          {s.overdue ? " (overdue)" : ""}
        </span>
      ))}
    </p>
  );
}
