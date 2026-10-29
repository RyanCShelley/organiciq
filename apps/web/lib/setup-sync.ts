import { syncJobWindow } from "./dates";
export type SetupSource = "ga4" | "gsc_pages" | "gsc_queries" | "se_ranking_search" | "se_ranking_ai" | "se_ranking_audit";
/** Saving a property starts its first reporting pull. Existing active jobs are
 * reused by the API's overlap guard; partial failures remain visible. */
export async function syncSelectedProperty(clientId: string, sources: SetupSource[]): Promise<string | null> {
  const errors: string[] = [];
  for (const source of sources) {
    try {
      const response = await fetch("/api/proxy/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clientId, source, ...syncJobWindow(90) }) });
      if (!response.ok && response.status !== 409) errors.push(source);
    } catch { errors.push(source); }
  }
  return errors.length ? `Property saved, but the initial pull could not start for ${errors.join(", ")}. Retry the initial sync below.` : null;
}
