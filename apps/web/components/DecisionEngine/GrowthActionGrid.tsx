import { Badge } from "@/components/ui/Badge";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { leverStatusLabel, type LeverSummary } from "@/lib/decision-engine";

function statusTone(status: string): { badge: "success" | "warning" | "neutral"; text: string } {
  if (status === "clear") {
    return { badge: "success", text: "text-status-success" };
  }
  if (status === "findings") {
    return { badge: "warning", text: "text-status-warning" };
  }
  return { badge: "neutral", text: "text-[var(--text-secondary)]" };
}

export function GrowthActionGrid({ levers }: { levers: LeverSummary[] }) {
  return (
    <section id="growth-actions" className="workspace-section scroll-mt-24">
      <SectionHeader
        title="Growth Action Evaluation"
        description="Status for each Growth Action lever in this period."
      />

      <div className="workspace-panel">
        <div className="metric-grid md:grid-cols-2 xl:grid-cols-3">
          {levers.map((lever) => {
            const tone = statusTone(lever.status);
            return (
              <div
                key={lever.lever}
                className="flex h-full flex-col rounded-[var(--radius-md)] border border-[var(--border)] p-[var(--card-padding)]"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="text-sm font-semibold leading-snug text-[var(--text-primary)]">
                    {lever.label}
                  </h3>
                  <Badge variant={tone.badge}>{leverStatusLabel(lever.status)}</Badge>
                </div>
                {lever.status === "findings" ? (
                  <p className={`mt-2 text-xs leading-relaxed ${tone.text}`}>
                    {lever.findings_count} finding{lever.findings_count === 1 ? "" : "s"} ·{" "}
                    {lever.recommended_actions_count} recommended action
                    {lever.recommended_actions_count === 1 ? "" : "s"}
                  </p>
                ) : lever.status === "clear" ? (
                  <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">
                    No findings after required data was evaluated.
                  </p>
                ) : (
                  <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">
                    Check data readiness before interpreting this lever.
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
