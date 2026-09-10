export type JobBadgeVariant = "neutral" | "success" | "warning" | "accent" | "danger";

/** Badge tone for a sync-job status, shared by the client and platform job tables. */
export function jobBadgeVariant(status: string): JobBadgeVariant {
  switch (status) {
    case "completed":
    case "succeeded":
      return "success";
    case "failed":
    case "error":
      return "danger";
    case "cancelled":
    case "canceled":
      return "warning";
    case "queued":
    case "running":
    case "fetching":
    case "staging":
    case "normalizing":
    case "validating":
      return "accent";
    default:
      return "neutral";
  }
}

export function jobStatusLabel(status: string): string {
  return status.replaceAll("_", " ");
}
