import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/api";
import { resolveClientId, resolveDateRange } from "@/lib/context";

type Decision = {
  id: string;
  decision_type: string;
  growth_action: string | null;
  diagnostic_layer: string;
  priority: string;
  status: string;
  query: string | null;
  page_url: string | null;
  diagnosis: string;
  recommended_action: string;
  success_metric: string;
  evidence_json: Record<string, unknown>;
  date_range_start: string;
  date_range_end: string;
};

const GROWTH_ACTION_LABELS: Record<string, string> = {
  internal_linking: "Internal Linking & Site Architecture",
  technical_seo: "Technical SEO & Indexation",
  serp_ctr: "SERP & CTR Optimization",
  structured_data_ai: "Structured Data, Entities & AI Visibility",
  conversion_path: "Conversion Path Optimization",
};

function labelGrowthAction(value: string | null): string {
  if (!value) return "Content Planning Signal";
  return GROWTH_ACTION_LABELS[value] ?? value;
}

function formatType(value: string): string {
  return value.replaceAll("_", " ");
}

async function evaluateDecisions(formData: FormData) {
  "use server";

  const clientId = String(formData.get("clientId") || "");
  const from = String(formData.get("from") || "");
  const to = String(formData.get("to") || "");
  if (!clientId || !from || !to) return;

  await apiFetch<{ created: Decision[]; skipped: number }>("/decisions/evaluate", {
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

  let decisions: Decision[] = [];
  let error: string | null = null;

  if (!clientId) {
    error = "Select a client to run the Decision Engine.";
  } else {
    try {
      decisions = await apiFetch<Decision[]>(
        `/decisions?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        { clientId },
      );
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load decisions";
    }
  }

  return (
    <section>
      <h1 className="text-2xl font-semibold">Decision Engine</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Visibility → Traffic → Conversion diagnostics from validated facts ({from} to {to}).
      </p>

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
            Generates stored recommendations mapped to Growth Actions. Re-runs skip duplicates for the same period.
          </p>
        </form>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
          {error}
        </p>
      ) : null}

      {!error && decisions.length === 0 ? (
        <p className="mt-6 rounded-lg border border-[var(--border)] px-3 py-2 text-sm text-[var(--muted)]">
          No decisions stored for this period yet. Click Evaluate period after dashboard data is synced.
        </p>
      ) : null}

      <div className="mt-6 space-y-4">
        {decisions.map((decision) => (
          <article
            key={decision.id}
            className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4"
          >
            <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wide text-[var(--muted)]">
              <span>{formatType(decision.priority)} priority</span>
              <span>·</span>
              <span>{formatType(decision.diagnostic_layer)}</span>
              <span>·</span>
              <span>{formatType(decision.decision_type)}</span>
              <span>·</span>
              <span>{labelGrowthAction(decision.growth_action)}</span>
            </div>
            <h2 className="mt-2 text-lg font-medium">{decision.diagnosis}</h2>
            <p className="mt-2 text-sm text-[var(--muted)]">{decision.recommended_action}</p>
            <p className="mt-3 text-sm">
              <span className="text-[var(--muted)]">Success metric:</span> {decision.success_metric}
            </p>
            {decision.query ? (
              <p className="mt-2 text-sm text-[var(--muted)]">
                Query: {decision.query}
                {decision.page_url ? ` · Page: ${decision.page_url}` : ""}
              </p>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
