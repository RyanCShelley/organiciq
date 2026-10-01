import { FieldLabel, Input } from "@/components/ui/Input";
import type { Client } from "@/lib/api";

/**
 * The lead goal at each checkpoint, editable.
 *
 * The projection builds the staircase and the dashboard reads whichever step
 * the client is standing on. A projection is a model, though, and sometimes a
 * step is visibly wrong — so each one can be corrected by hand. Corrections are
 * stored apart from the frozen projection, so re-running it does not discard
 * them.
 */

const MONTH_LABEL: Record<number, string> = {
  0: "Baseline",
  3: "3 months",
  6: "6 months",
  9: "9 months",
  12: "12 months",
};

function formatDue(iso: string | null): string {
  if (!iso) return "";
  const parsed = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function LeadGoalSchedule({ client }: { client: Client }) {
  const checkpoints = client.baseline_projection_json?.checkpoints ?? [];
  const overrides = client.lead_goal_overrides ?? {};

  if (checkpoints.length === 0) {
    return (
      <p className="text-xs text-[var(--text-secondary)]">
        No projection yet. Build one from the baseline and the goals for each checkpoint
        appear here, editable.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-[var(--text-secondary)]">
        The dashboard shows whichever of these the client is working toward now, not the
        twelve-month figure — a thirty-day review judged against next year&rsquo;s target
        makes an on-track client look like a failing one. Blank uses the projected value;
        a number here replaces it and survives re-running the projection.
      </p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {[...checkpoints]
          .sort((a, b) => a.month - b.month)
          .map((checkpoint) => {
            const projected = Math.round(checkpoint.monthly_leads);
            const override = overrides[String(checkpoint.month)];
            return (
              <div key={checkpoint.month} className="flex flex-col gap-1">
                <FieldLabel label={MONTH_LABEL[checkpoint.month] ?? `${checkpoint.month} months`}>
                  <Input
                    name={`lead_goal_${checkpoint.month}`}
                    type="number"
                    min={0}
                    defaultValue={override ?? ""}
                    placeholder={String(projected)}
                  />
                </FieldLabel>
                <span className="text-[11px] text-[var(--text-tertiary)]">
                  Projected {projected.toLocaleString()}
                </span>
              </div>
            );
          })}
      </div>
    </div>
  );
}
