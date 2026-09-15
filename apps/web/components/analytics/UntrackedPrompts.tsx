"use client";

import { Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { DataTable } from "@/components/analytics/DataTable";
import { Alert } from "@/components/ui/Alert";
import { Select } from "@/components/ui/Input";

export type UntrackedPrompt = {
  prompt: string;
  engine: string;
  volume: number | null;
  appearance_type: string | null;
  answer_links: string[];
};

export type UntrackedPromptsPayload = {
  /** This client's ceiling, set in Client settings. */
  max_prompts: number;
  credits_per_prompt: number;
  /** engine -> when it was last fetched. Each engine is billed separately. */
  engines_fetched: Record<string, string | null>;
  discovered_prompts: number;
  tracked_prompts: number;
  untracked_total: number;
  items: UntrackedPrompt[];
};

/**
 * Priced per *returned prompt*, not per request — unlike every other lookup in
 * the app. The API's own default of 100 is 20,000 credits, so the count is a
 * deliberate choice here and the cost is stated before the button is pressed.
 *
 * The selectable counts are bounded by the client's own ceiling, which the
 * server enforces independently.
 */
const FALLBACK_CREDITS_PER_PROMPT = 200;
const COUNT_STEPS = [5, 10, 25, 50];

const ENGINES = [
  { value: "chatgpt", label: "ChatGPT" },
  { value: "perplexity", label: "Perplexity" },
  { value: "gemini", label: "Gemini" },
  { value: "ai-overview", label: "AI Overview" },
  { value: "ai-mode", label: "AI Mode" },
];

const POLL_INTERVAL_MS = 4000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;
const ACTIVE_STATUSES = new Set([
  "queued",
  "fetching",
  "staging",
  "normalizing",
  "validating",
]);

function formatNum(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(1);
}

function engineLabel(value: string): string {
  return ENGINES.find((e) => e.value === value)?.label ?? value;
}

export function UntrackedPrompts({
  clientId,
  data,
  loadError = null,
}: {
  clientId: string;
  data: UntrackedPromptsPayload;
  loadError?: string | null;
}) {
  const router = useRouter();
  const maxPrompts = data.max_prompts || 5;
  const creditsPerPrompt = data.credits_per_prompt || FALLBACK_CREDITS_PER_PROMPT;
  // Never offer more than this client is allowed to spend.
  const counts = COUNT_STEPS.filter((n) => n <= maxPrompts);
  const options = counts.length > 0 ? counts : [maxPrompts];

  const [engine, setEngine] = useState(ENGINES[0].value);
  const [count, setCount] = useState(options[0]);
  const [pending, setPending] = useState(false);
  const [watching, setWatching] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startedAt = useRef<number | null>(null);

  const cost = count * creditsPerPrompt;
  const fetchedEngines = Object.keys(data.engines_fetched);

  const checkJob = useCallback(async () => {
    const res = await fetch(`/api/proxy/jobs?clientId=${encodeURIComponent(clientId)}`);
    if (!res.ok) return;
    const jobs: Array<{ source: string; status: string; error_message: string | null }> =
      await res.json();
    const latest = jobs.find((job) => job.source === "se_ranking_ai_search");
    if (!latest || ACTIVE_STATUSES.has(latest.status)) return;

    setWatching(false);
    startedAt.current = null;
    if (latest.status === "failed") {
      setMessage(null);
      setError(latest.error_message || "The lookup failed. Check Sync jobs for details.");
      return;
    }
    setError(null);
    setMessage("Lookup finished.");
    router.refresh();
  }, [clientId, router]);

  useEffect(() => {
    if (!watching) return;
    const timer = setInterval(() => {
      if (startedAt.current && Date.now() - startedAt.current > POLL_TIMEOUT_MS) {
        setWatching(false);
        startedAt.current = null;
        setMessage(null);
        setError("Still running after 5 minutes — check Sync jobs.");
        return;
      }
      void checkJob();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [watching, checkJob]);

  async function run() {
    setError(null);
    setMessage(null);
    setPending(true);

    const today = new Date().toISOString().slice(0, 10);
    const res = await fetch("/api/proxy/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clientId,
        source: "se_ranking_ai_search",
        start_date: today,
        end_date: today,
        params: { engine, limit: count },
      }),
    });

    setPending(false);
    if (!res.ok) {
      setError((await res.text()) || "Failed to queue the lookup");
      return;
    }
    setMessage(`Queued ${engineLabel(engine)} — watching for results…`);
    startedAt.current = Date.now();
    setWatching(true);
  }

  return (
    <div className="card mt-4 p-[var(--card-padding)]">
      <div className="min-w-0">
        <h3 className="font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
          Untracked prompts
        </h3>
        <p className="mt-1 text-[12.5px] text-[var(--text-tertiary)]">
          {fetchedEngines.length > 0 ? (
            <>
              {data.untracked_total.toLocaleString()} of{" "}
              {data.discovered_prompts.toLocaleString()} discovered prompts aren&rsquo;t
              tracked · checked {fetchedEngines.map(engineLabel).join(", ")}
            </>
          ) : (
            <>
              Finds prompts the brand appears in that aren&rsquo;t on the watch list. One
              engine per run, up to {maxPrompts} prompts — raise that per client in
              Client settings.
            </>
          )}
        </p>
      </div>

      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="field-label">
          Engine
          <Select value={engine} onChange={(e) => setEngine(e.target.value)}>
            {ENGINES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
                {data.engines_fetched[option.value] !== undefined ? " · fetched" : ""}
              </option>
            ))}
          </Select>
        </label>

        <label className="field-label">
          Prompts
          <Select value={String(count)} onChange={(e) => setCount(Number(e.target.value))}>
            {options.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </label>

        <button
          type="button"
          className="btn btn-secondary gap-2"
          onClick={run}
          disabled={pending || watching}
        >
          <Sparkles className="h-3.5 w-3.5" aria-hidden />
          {pending ? "Queueing…" : watching ? "Running…" : "Find untracked prompts"}
        </button>

        {/* Stated in full before the click: this is billed per prompt returned,
            which is unlike every other lookup in the app. */}
        <span className="pb-1.5 text-[12.5px] font-semibold text-[var(--warning)]">
          ≈{cost.toLocaleString()} credits ({count} × {creditsPerPrompt})
        </span>
      </div>

      {loadError ? (
        <Alert variant="danger" className="mt-3">
          Could not load untracked prompts: {loadError}
        </Alert>
      ) : null}
      {error ? (
        <Alert variant="danger" className="mt-3">
          {error}
        </Alert>
      ) : null}
      {message ? (
        <Alert variant="success" className="mt-3">
          {message}
        </Alert>
      ) : null}

      {data.items.length > 0 ? (
        <div className="mt-3">
          <DataTable
            columns={[
              {
                key: "prompt",
                header: "Prompt",
                render: (row) => (
                  <span className="block max-w-[26rem] truncate" title={row.prompt}>
                    {row.prompt}
                  </span>
                ),
              },
              {
                key: "engine",
                header: "Engine",
                render: (row) => engineLabel(row.engine),
              },
              {
                key: "volume",
                header: "Volume",
                align: "right",
                render: (row) => formatNum(row.volume),
              },
              {
                key: "appearance_type",
                header: "Appears as",
                render: (row) =>
                  row.appearance_type ? (
                    <span className="badge badge-neutral">{row.appearance_type}</span>
                  ) : (
                    <span className="text-[var(--text-tertiary)]">—</span>
                  ),
              },
            ]}
            rows={data.items}
            getRowKey={(row) => `${row.engine}-${row.prompt}`}
          />
          {data.untracked_total > data.items.length ? (
            <p className="mt-2 text-xs text-[var(--text-tertiary)]">
              Showing the top {data.items.length.toLocaleString()} by volume of{" "}
              {data.untracked_total.toLocaleString()}.
            </p>
          ) : null}
        </div>
      ) : fetchedEngines.length > 0 ? (
        <Alert variant="info" className="mt-3">
          Every prompt found for {fetchedEngines.map(engineLabel).join(", ")} is already
          tracked.
        </Alert>
      ) : null}
    </div>
  );
}
