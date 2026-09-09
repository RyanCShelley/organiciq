export const ANNOTATION_CSV_TEMPLATE = `date,annotation_type,growth_action,description,page_url,success_metric,completed_at,measurement_start_date,measurement_end_date,result,notes,baseline_sessions,baseline_leads,baseline_impressions,baseline_clicks,post_sessions,post_leads,post_impressions,post_clicks
2025-06-01,growth_action,serp_ctr,Rewrote title and meta for service page,https://example.com/services,CTR recovery to expected,2025-06-05,2025-06-06,2025-07-05,not_yet_measured,Imported historical work,,,,,
2025-03-15,content_published,,Published pillar page on industrial pumps,https://example.com/guides/pumps,Organic sessions + leads,2025-03-20,2025-03-21,2025-04-20,improved,Q1 content push,1200,8,45000,900,1450,12,52000,1100
`;

export const ANNOTATION_TYPES = [
  { value: "growth_action", label: "Growth Action" },
  { value: "content_published", label: "Content Published" },
  { value: "content_updated", label: "Content Updated" },
  { value: "technical_change", label: "Technical Change" },
  { value: "website_change", label: "Website Change" },
  { value: "conversion_change", label: "Conversion Change" },
  { value: "campaign_change", label: "Campaign Change" },
  { value: "algorithm_event", label: "Algorithm / Event" },
  { value: "manual_note", label: "Manual Note" },
] as const;

export const GROWTH_ACTIONS = [
  { value: "", label: "— none —" },
  { value: "internal_linking", label: "Internal Linking" },
  { value: "technical_seo", label: "Technical SEO" },
  { value: "serp_ctr", label: "SERP CTR" },
  { value: "structured_data_ai", label: "Search & AI Visibility" },
  { value: "conversion_path", label: "Conversion Path" },
] as const;

export type AnnotationRow = {
  id: string;
  date: string;
  annotation_type: string;
  growth_action: string | null;
  description: string;
  page_url: string | null;
  success_metric: string | null;
  completed_at: string | null;
  measurement_start_date: string | null;
  measurement_end_date: string | null;
  result: string;
  notes: string | null;
  baseline_metrics_json: Record<string, unknown>;
  post_action_metrics_json: Record<string, unknown>;
  impact_summary_json: {
    deltas?: Record<string, number | null>;
    suggested_result?: string;
    baseline?: Record<string, number | null>;
    post?: Record<string, number | null>;
  };
};

export function annotationTypeLabel(value: string): string {
  return ANNOTATION_TYPES.find((row) => row.value === value)?.label ?? value.replaceAll("_", " ");
}

export function resultLabel(value: string): string {
  switch (value) {
    case "improved":
      return "Improved";
    case "declined":
      return "Declined";
    case "no_meaningful_change":
      return "No meaningful change";
    case "not_enough_data":
      return "Not enough data";
    case "not_yet_measured":
      return "Not yet measured";
    default:
      return value.replaceAll("_", " ");
  }
}

export function formatDelta(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}
