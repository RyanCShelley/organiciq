import { Badge } from "@/components/ui/Badge";
import {
  annotationTypeLabel,
  formatDelta,
  resultLabel,
  type AnnotationRow,
} from "@/lib/annotations";

function resultVariant(
  result: string,
): "success" | "warning" | "neutral" | "accent" {
  switch (result) {
    case "improved":
      return "success";
    case "declined":
      return "warning";
    case "not_yet_measured":
      return "accent";
    case "no_meaningful_change":
    case "not_enough_data":
      return "neutral";
    default:
      return "neutral";
  }
}

function metricCell(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
  }
  return String(value);
}

export function AnnotationsTable({ rows }: { rows: AnnotationRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-[var(--text-secondary)]">
        No annotations yet. Upload historical work or add one above.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[960px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-[0.04em] text-[var(--text-tertiary)]">
            <th className="px-2 py-2 font-semibold">Date</th>
            <th className="px-2 py-2 font-semibold">Type</th>
            <th className="px-2 py-2 font-semibold">Change</th>
            <th className="px-2 py-2 font-semibold">Impact</th>
            <th className="px-2 py-2 font-semibold">Result</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const deltas = row.impact_summary_json?.deltas ?? {};
            const baseline = row.impact_summary_json?.baseline ?? row.baseline_metrics_json;
            const post = row.impact_summary_json?.post ?? row.post_action_metrics_json;
            return (
              <tr key={row.id} className="border-b border-[var(--border)] align-top">
                <td className="px-2 py-3 whitespace-nowrap text-[var(--text-secondary)]">
                  {row.date}
                  {row.completed_at ? (
                    <div className="text-xs text-[var(--text-tertiary)]">Done {row.completed_at}</div>
                  ) : null}
                </td>
                <td className="px-2 py-3">
                  <div className="font-medium">{annotationTypeLabel(row.annotation_type)}</div>
                  {row.growth_action ? (
                    <div className="text-xs text-[var(--text-tertiary)]">
                      {row.growth_action.replaceAll("_", " ")}
                    </div>
                  ) : null}
                </td>
                <td className="px-2 py-3">
                  <div className="font-medium text-[var(--text-primary)]">{row.description}</div>
                  {row.page_url ? (
                    <a
                      href={row.page_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-0.5 block truncate text-xs text-[var(--brand-teal-hover)] underline"
                    >
                      {row.page_url}
                    </a>
                  ) : null}
                  {row.success_metric ? (
                    <div className="mt-1 text-xs text-[var(--text-secondary)]">
                      Success: {row.success_metric}
                    </div>
                  ) : null}
                </td>
                <td className="px-2 py-3">
                  <div className="grid gap-1 text-xs text-[var(--text-secondary)]">
                    <div>
                      Sessions {metricCell(baseline?.sessions)} → {metricCell(post?.sessions)}{" "}
                      <span className="font-medium text-[var(--text-primary)]">
                        ({formatDelta(deltas.sessions_change_pct as number | null | undefined)})
                      </span>
                    </div>
                    <div>
                      Leads {metricCell(baseline?.leads)} → {metricCell(post?.leads)}{" "}
                      <span className="font-medium text-[var(--text-primary)]">
                        ({formatDelta(deltas.leads_change_pct as number | null | undefined)})
                      </span>
                    </div>
                    <div>
                      Clicks {metricCell(baseline?.clicks)} → {metricCell(post?.clicks)}{" "}
                      <span className="font-medium text-[var(--text-primary)]">
                        ({formatDelta(deltas.clicks_change_pct as number | null | undefined)})
                      </span>
                    </div>
                    {row.measurement_start_date && row.measurement_end_date ? (
                      <div className="text-[var(--text-tertiary)]">
                        Window {row.measurement_start_date} → {row.measurement_end_date}
                      </div>
                    ) : (
                      <div className="text-[var(--text-tertiary)]">No measurement window yet</div>
                    )}
                  </div>
                </td>
                <td className="px-2 py-3">
                  <Badge variant={resultVariant(row.result)}>{resultLabel(row.result)}</Badge>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
