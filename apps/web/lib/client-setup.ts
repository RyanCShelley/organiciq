import type { SetupState } from "../components/SetupChecklist";
export const SETUP_STAGES = [
  { label: "General information", keys: ["account"] },
  { label: "Connections", keys: ["sources"] },
  { label: "Initial sync", keys: ["pull"] },
  { label: "Conversions", keys: ["leads", "conversion_pages"] },
  { label: "Page mapping", keys: ["page_stages", "keyword_targets"] },
  { label: "Goals & baseline", keys: ["baseline"], optional: true },
  { label: "Review & finish", keys: ["first_run"] },
] as const;
export function setupProgress(state: SetupState) {
  const stages = SETUP_STAGES.map(stage => ({ ...stage, done: stage.keys.every(key => state.steps.some(s => s.key === key && s.done)) }));
  const next = stages.findIndex(stage => !stage.done && !("optional" in stage && stage.optional));
  return { stages, done: stages.filter(s => s.done).length, total: stages.length, next: next < 0 ? 6 : next, complete: next < 0 };
}
export function pageIdentity(value: string): string {
  try { const u = new URL(value); return `${u.hostname.toLowerCase().replace(/^www\./, "")}${u.pathname.replace(/\/+$/, "") || "/"}`; } catch { return value; }
}
