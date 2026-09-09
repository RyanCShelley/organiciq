import Link from "next/link";

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

export function GrowthActionGrid({
  levers,
  contentOppHref,
  contentOppCount,
}: {
  levers: LeverSummary[];
  contentOppHref: string;
  contentOppCount: number;
}) {
  const contentOppStatus = contentOppCount > 0 ? "findings" : "clear";
  const contentOppTone = statusTone(contentOppStatus);

  return (
    <section id="growth-actions" className="workspace-section scroll-mt-24">
      <SectionHeader
        title="Growth Action Evaluation"
        description="Status for each Growth Action lever in this period, plus Content Opp."
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

          <Link
            href={contentOppHref}
            className="flex h-full flex-col rounded-[var(--radius-md)] border border-[var(--border)] p-[var(--card-padding)] transition-colors hover:border-[var(--accent)]/50 hover:bg-[var(--accent)]/5"
          >
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-sm font-semibold leading-snug text-[var(--text-primary)]">
                Content Opp
              </h3>
              <Badge variant={contentOppTone.badge}>
                {contentOppCount > 0 ? "Opportunities" : "Clear"}
              </Badge>
            </div>
            {contentOppCount > 0 ? (
              <p className={`mt-2 text-xs leading-relaxed ${contentOppTone.text}`}>
                {contentOppCount} striking-distance opportunit
                {contentOppCount === 1 ? "y" : "ies"} · open Content Opp
              </p>
            ) : (
              <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">
                No content opportunities in this window. Open Content Opp to review.
              </p>
            )}
          </Link>
        </div>
      </div>
    </section>
  );
}
