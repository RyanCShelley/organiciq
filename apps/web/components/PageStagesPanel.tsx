"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import { Alert } from "@/components/ui/Alert";

export type PageStageRow = {
  normalized_url: string;
  title: string | null;
  sessions: number;
  stage: string | null;
  suggested_stage: string | null;
  confidence: string | null;
  rationale: string | null;
  confirmed: boolean;
};

export type PageStagePayload = {
  model_ready: boolean;
  coverage: {
    pages: number;
    confirmed_pages: number;
    sessions: number;
    confirmed_sessions: number;
    floor: number;
  };
  pages: PageStageRow[];
};

const STAGES = [
  { value: "tofu", label: "Early — just learning" },
  { value: "mofu", label: "Comparing options" },
  { value: "bofu", label: "Ready to buy" },
] as const;

const CONFIDENCE_CHIP: Record<string, string> = {
  high: "bg-[#E5F4EC] text-[#15784F]",
  medium: "bg-[#FDF1E3] text-[#8A4B08]",
  low: "bg-[#FDF1E3] text-[#8A4B08]",
};

function path(url: string): string {
  return url.replace(/^https?:\/\/[^/]+/, "") || "/";
}

/**
 * Label the landing pages by where their reader is.
 *
 * L3's missing input. A model reads each page and proposes; this is where
 * somebody agrees or disagrees, and only what they agree to is read by the
 * engine — the same rule as conversion pages, which exist because guessing a
 * page's role from its URL was wrong often enough to hide how often.
 *
 * Progress is measured in sessions rather than rows. Thirty pages ticked can
 * be five percent of the traffic, and a share computed over five percent of
 * the traffic is a real number that says nothing about the site.
 */
export function PageStagesPanel({
  clientId,
  initial,
}: {
  clientId: string;
  initial: PageStagePayload;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});

  const rows = initial.pages;
  const coverage = initial.coverage;

  /** What a row would be confirmed as: an edit, else the confirmed stage, else the suggestion. */
  function chosen(row: PageStageRow): string {
    return edits[row.normalized_url] ?? row.stage ?? row.suggested_stage ?? "";
  }

  const pendingCount = useMemo(
    () =>
      rows.filter((row) => {
        const value = chosen(row);
        return value && (!row.confirmed || value !== row.stage);
      }).length,
    [rows, edits],
  );

  const coveragePct = coverage.sessions
    ? (coverage.confirmed_sessions / coverage.sessions) * 100
    : 0;
  const floorPct = coverage.floor * 100;

  function suggest() {
    setError(null);
    setNote(null);
    startTransition(async () => {
      const res = await fetch("/api/proxy/page-stages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail || "The model could not read the pages");
        return;
      }
      setNote(
        `Read ${body.pages} pages. Nothing is confirmed yet — check each one below.`,
      );
      router.refresh();
    });
  }

  function save() {
    setError(null);
    setNote(null);
    const stages = rows
      .map((row) => ({ normalized_url: row.normalized_url, stage: chosen(row) }))
      .filter((row) => row.stage);
    startTransition(async () => {
      const res = await fetch("/api/proxy/page-stages", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId, stages }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail || "Those did not save");
        return;
      }
      setEdits({});
      setNote(`Confirmed ${body.confirmed}. The engine reads these.`);
      router.refresh();
    });
  }

  /** Take every suggestion the model was sure about, to be reviewed in bulk. */
  function acceptHighConfidence() {
    const next = { ...edits };
    for (const row of rows) {
      if (row.confidence === "high" && row.suggested_stage && !row.confirmed) {
        next[row.normalized_url] = row.suggested_stage;
      }
    }
    setEdits(next);
  }

  if (rows.length === 0) {
    return (
      <p className="text-[14px] text-[var(--text-secondary)]">
        No landing page has both crawl data and organic sessions in the last 90
        days, so there is nothing to label yet.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {error ? <Alert variant="danger">{error}</Alert> : null}
      {note ? <Alert variant="success">{note}</Alert> : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-[13px] text-[var(--text-secondary)]">
          <span className="font-semibold text-[var(--text-primary)]">
            {coveragePct.toFixed(0)}% of organic sessions
          </span>{" "}
          sit on a page with a confirmed stage ({coverage.confirmed_pages} of{" "}
          {coverage.pages} pages).{" "}
          {coveragePct >= floorPct
            ? "That is enough for the next-step test to run."
            : `The next-step test needs ${floorPct.toFixed(0)}%.`}
        </div>
        <div className="flex flex-wrap gap-2">
          {initial.model_ready ? (
            <button
              type="button"
              onClick={suggest}
              disabled={pending}
              className="inline-flex min-h-[36px] items-center rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3.5 text-[13px] font-semibold disabled:opacity-60"
            >
              {pending ? "Reading…" : "Read the pages"}
            </button>
          ) : null}
          <button
            type="button"
            onClick={acceptHighConfidence}
            disabled={pending}
            className="inline-flex min-h-[36px] items-center rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3.5 text-[13px] font-semibold disabled:opacity-60"
          >
            Take the confident ones
          </button>
          <button
            type="button"
            onClick={save}
            disabled={pending || pendingCount === 0}
            className="inline-flex min-h-[36px] items-center rounded-lg border border-[var(--brand-teal-deep)] bg-[var(--surface)] px-3.5 text-[13px] font-semibold disabled:opacity-60"
          >
            Confirm {pendingCount || ""}
          </button>
        </div>
      </div>

      {!initial.model_ready ? (
        <p className="rounded-[8px] bg-[var(--surface-muted)] px-3 py-2 text-[13px] text-[var(--text-secondary)]">
          No model is configured, so there is nothing to read the pages for you.
          Set <code>ANTHROPIC_API_KEY</code> on the API, or set the stages by
          hand below.
        </p>
      ) : null}

      <ul>
        {rows.map((row) => {
          const value = chosen(row);
          const changed = value && (!row.confirmed || value !== row.stage);
          return (
            <li
              key={row.normalized_url}
              className="grid gap-x-4 gap-y-2 border-t border-[var(--border)] py-3 sm:grid-cols-[minmax(0,1fr)_auto]"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[14px] font-semibold text-[var(--text-primary)]">
                    {row.title || path(row.normalized_url)}
                  </span>
                  {row.confirmed && !changed ? (
                    <span className="rounded-full bg-[#E5F4EC] px-2 py-0.5 text-[11px] font-semibold text-[#15784F]">
                      Confirmed
                    </span>
                  ) : null}
                  {row.suggested_stage && row.confidence ? (
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                        CONFIDENCE_CHIP[row.confidence] ?? CONFIDENCE_CHIP.low
                      }`}
                    >
                      Model: {row.confidence}
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 break-words font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]">
                  {path(row.normalized_url)} · {Math.round(row.sessions)} sessions
                </p>
                {/* The model's reason, so disagreeing with it is possible. */}
                {row.rationale ? (
                  <p className="mt-1 text-[12.5px] italic text-[var(--text-secondary)]">
                    {row.rationale}
                  </p>
                ) : null}
              </div>

              <div className="flex items-start">
                <label className="sr-only" htmlFor={`stage-${row.normalized_url}`}>
                  Stage for {path(row.normalized_url)}
                </label>
                <select
                  id={`stage-${row.normalized_url}`}
                  className="min-h-[36px] rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-[13px]"
                  value={value}
                  onChange={(e) =>
                    setEdits((prev) => ({
                      ...prev,
                      [row.normalized_url]: e.target.value,
                    }))
                  }
                >
                  <option value="">Not set</option>
                  {STAGES.map((stage) => (
                    <option key={stage.value} value={stage.value}>
                      {stage.label}
                    </option>
                  ))}
                </select>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
