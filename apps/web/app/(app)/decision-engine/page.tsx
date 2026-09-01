import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/api";
import { resolveClientId, resolveDateRange } from "@/lib/context";

type LeverSummary = {
  lever: string;
  label: string;
  findings_count: number;
  status: string;
};

type Recommendation = {
  rule_key: string;
  lever: string;
  label: string;
  stage: string;
  diagnosis: string;
  recommended_action: string;
  success_metric: string;
  priority_score: number;
  impact: number;
  confidence: number;
  urgency: number;
  effort: number;
  page_url: string | null;
  query: string | null;
  evidence_json: Record<string, unknown>;
};

type DiagnoseResponse = {
  ready: boolean;
  message: string | null;
  readiness: Record<string, boolean>;
  formula: string;
  levers: LeverSummary[];
  recommendations: Recommendation[];
};

const STAGE_LABELS: Record<string, string> = {
  visibility: "Visibility",
  traffic: "Traffic",
  conversion: "Outcomes",
};

function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

function readinessLabel(key: string): string {
  if (key === "search_console") return "Search Console";
  if (key === "crawl_audit") return "Crawl / Audit";
  return key;
}

function scoreBar(value: number): string {
  return `${Math.max(0, Math.min(100, value))}%`;
}

function formatEvidence(evidence: Record<string, unknown>): string {
  const parts: string[] = [];
  if (typeof evidence.position === "number") parts.push(`position ${evidence.position}`);
  if (typeof evidence.inbound_internal_links === "number") {
    parts.push(`${evidence.inbound_internal_links} inbound internal links`);
    if (typeof evidence.link_floor === "number") parts.push(`(floor ${evidence.link_floor})`);
  }
  if (typeof evidence.impressions === "number") parts.push(`${evidence.impressions.toLocaleString()} impr`);
  if (typeof evidence.lead_rate_change_pct === "number") {
    parts.push(`Lead rate ${evidence.lead_rate_change_pct}%`);
  }
  if (typeof evidence.sessions_change_pct === "number") {
    parts.push(`while sessions ${evidence.sessions_change_pct}%`);
  }
  if (evidence.tracking_validated) parts.push("tracking-validated");
  if (typeof evidence.ctr_percent === "number" && typeof evidence.expected_ctr_percent === "number") {
    parts.push(`CTR ${evidence.ctr_percent}% vs expected ${evidence.expected_ctr_percent}%`);
  }
  return parts.join(", ");
}

async function evaluateDecisions(formData: FormData) {
  "use server";

  const clientId = String(formData.get("clientId") || "");
  const from = String(formData.get("from") || "");
  const to = String(formData.get("to") || "");
  if (!clientId || !from || !to) return;

  await apiFetch("/decisions/evaluate", {
    method: "POST",
    clientId,
    body: { from, to },
  });
  revalidatePath("/decision-engine");
}

export default async function DecisionEnginePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const clientId = await resolveClientId(params);
  const { from, to } = await resolveDateRange(params);

  let data: DiagnoseResponse | null = null;
  let error: string | null = null;

  if (!clientId) {
    error = "Select a client to run the Decision Engine.";
  } else {
    try {
      data = await apiFetch<DiagnoseResponse>(
        `/decisions/diagnose?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        { clientId },
      );
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load Decision Engine";
    }
  }

  return (
    <section>
      <h1 className="text-2xl font-semibold">Decision Engine</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Six growth levers · diagnoses the constrained stage, maps each finding to one lever, ranks by impact.
      </p>

      {data ? (
        <div className="mt-4 flex flex-wrap gap-3 text-sm">
          {Object.entries(data.readiness).map(([key, ready]) => (
            <span
              key={key}
              className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] px-3 py-1"
            >
              <span className={`inline-block h-2 w-2 rounded-full ${ready ? "bg-emerald-400" : "bg-amber-400"}`} />
              {readinessLabel(key)}
            </span>
          ))}
        </div>
      ) : null}

      {clientId ? (
        <form action={evaluateDecisions} className="mt-4 flex flex-wrap items-end gap-3">
          <input type="hidden" name="clientId" value={clientId} />
          <input type="hidden" name="from" value={from} />
          <input type="hidden" name="to" value={to} />
          <button
            type="submit"
            className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-black hover:bg-white/90"
          >
            Evaluate period
          </button>
          <p className="text-sm text-[var(--muted)]">
            {from} to {to} · ranked by {data?.formula ?? "impact-weighted score"}
          </p>
        </form>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
          {error}
        </p>
      ) : null}

      {data && !data.ready ? (
        <p className="mt-4 rounded-lg border border-[var(--border)] px-3 py-2 text-sm text-[var(--muted)]">
          {data.message ?? "Decision Engine is not ready for this client and date range."}
        </p>
      ) : null}

      {data?.ready ? (
        <>
          <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data.levers.map((lever) => (
              <div
                key={lever.lever}
                className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-sm font-medium">{lever.label}</h2>
                  <span
                    className={`inline-flex items-center gap-2 text-xs ${
                      lever.status === "clear" ? "text-emerald-300" : "text-amber-200"
                    }`}
                  >
                    <span
                      className={`inline-block h-2 w-2 rounded-full ${
                        lever.status === "clear" ? "bg-emerald-400" : "bg-amber-400"
                      }`}
                    />
                    {lever.status === "clear" ? "clear" : `${lever.findings_count} findings`}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-8">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-medium">Recommendations</h2>
              <p className="text-sm text-[var(--muted)]">
                {data.recommendations.length} shown · ranked by {data.formula}
              </p>
            </div>

            {data.recommendations.length === 0 ? (
              <p className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm text-[var(--muted)]">
                No findings matched the configured rules for this period.
              </p>
            ) : (
              <div className="space-y-4">
                {data.recommendations.map((item) => (
                  <article
                    key={item.rule_key}
                    className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4"
                  >
                    <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wide text-[var(--muted)]">
                      <span className="rounded-full border border-[var(--border)] px-2 py-0.5">
                        {stageLabel(item.stage)}
                      </span>
                      <span>{item.label}</span>
                      <span>·</span>
                      <span>Priority {Math.round(item.priority_score)}</span>
                    </div>
                    <h3 className="mt-2 text-lg font-medium">{item.diagnosis}</h3>
                    <p className="mt-2 text-sm text-[var(--muted)]">
                      {formatEvidence(item.evidence_json)}
                    </p>
                    <p className="mt-3 text-sm">
                      <span className="text-[var(--muted)]">Action:</span> {item.recommended_action}
                    </p>
                    <p className="mt-1 text-sm text-[var(--muted)]">
                      {item.priority_score >= 70 ? "High priority" : "Priority recommendation"}
                    </p>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      {[
                        ["Impact", item.impact],
                        ["Confidence", item.confidence],
                        ["Urgency", item.urgency],
                        ["Effort", item.effort],
                      ].map(([label, value]) => (
                        <div key={String(label)}>
                          <div className="mb-1 flex justify-between text-xs text-[var(--muted)]">
                            <span>{label}</span>
                            <span>{value}</span>
                          </div>
                          <div className="h-2 rounded-full bg-white/10">
                            <div
                              className="h-2 rounded-full bg-white/70"
                              style={{ width: scoreBar(Number(value)) }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        </>
      ) : null}
    </section>
  );
}
