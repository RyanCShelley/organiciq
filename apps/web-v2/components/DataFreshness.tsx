import { apiFetch } from "@/lib/api";

export type Source = { key: string; label: string; through: string | null; age_days: number | null; overdue: boolean };

const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** The newest data each source holds, so a stale pull is visible before anyone reads a list built on it. */
export function freshnessFor(clientId: string): Promise<Source[] | null> {
  return apiFetch<Source[]>("/v2/engine/freshness", { clientId }).catch(() => null);
}

/** Pass `pending` (from freshnessFor, started early) so the lookup runs beside the page's own, not after it. */
export async function DataFreshness({ clientId, pending }: { clientId: string; pending?: Promise<Source[] | null> }) {
  const sources = await (pending ?? freshnessFor(clientId));
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
