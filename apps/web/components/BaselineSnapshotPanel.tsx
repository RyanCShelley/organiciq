"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  applyBaselineFromGa4Action,
  previewBaselineFromGa4Action,
  type BaselineProjection,
  type BaselineSnapshotPreview,
} from "@/app/(app)/baseline-actions";
import { Alert } from "@/components/ui/Alert";
import { FieldLabel, Input, Select } from "@/components/ui/Input";

function formatNum(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return Number.isInteger(value)
    ? value.toLocaleString()
    : value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

const LOOKBACK_OPTIONS = [
  { value: 90, label: "90 days (recommended average)" },
  { value: 60, label: "60 days" },
  { value: 30, label: "30 days" },
];

/** A frozen projection older than this reads as stale and prompts a re-run. */
const STALE_AFTER_DAYS = 365;

function daysSince(iso: string): number | null {
  const then = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(then.getTime())) return null;
  return Math.floor((Date.now() - then.getTime()) / 86_400_000);
}

export function BaselineSnapshotPanel({
  clientId,
  clientSlug,
  hasLeadConversions,
  savedAsOf,
  savedProjection,
}: {
  clientId: string;
  clientSlug: string;
  hasLeadConversions: boolean;
  savedAsOf?: string | null;
  savedProjection?: BaselineProjection | null;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [preview, setPreview] = useState<BaselineSnapshotPreview | null>(null);
  const [goal, setGoal] = useState<string>("");
  const [asOf, setAsOf] = useState<string>(savedAsOf ?? "");
  const [lookbackDays, setLookbackDays] = useState<number>(90);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const projectionAge = savedProjection ? daysSince(savedProjection.generated_on) : null;
  const projectionStale = projectionAge !== null && projectionAge >= STALE_AFTER_DAYS;

  if (!hasLeadConversions) {
    return (
      <Alert variant="info">
        Declare lead conversion sources first, then create the baseline snapshot from GA4.{" "}
        <Link
          href={`/clients/${clientSlug}/conversions`}
          className="font-medium text-[var(--brand-teal-hover)] underline"
        >
          Manage conversions
        </Link>
      </Alert>
    );
  }

  return (
    <div className="space-y-4 border-t border-[var(--border)] pt-4">
      <div>
        <p className="text-sm font-medium text-[var(--text-primary)]">
          Build snapshot from GA4
        </p>
        <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
          Averages sessions and lead events over the window ending on the baseline date,
          scales to monthly, then projects a 12‑month lead goal from the{" "}
          {preview?.plan_label ?? savedProjection?.plan_label ?? "tier"} calculator curve.
        </p>
      </div>

      {savedProjection ? (
        <div
          className={
            projectionStale
              ? "alert alert-warning"
              : "rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2"
          }
        >
          <p className="text-xs">
            <span className="font-semibold">Saved projection</span> — baseline{" "}
            {savedProjection.baseline_as_of}, generated {savedProjection.generated_on}
            {projectionAge !== null ? ` (${projectionAge} days ago)` : ""}.
            {projectionStale
              ? " Over a year old — re-run to refresh the benchmarks."
              : " Benchmarks stay frozen until you re-run."}
          </p>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-[repeat(2,minmax(0,1fr))_auto] sm:items-end">
        <FieldLabel label="Baseline date">
          <Input
            type="date"
            value={asOf}
            onChange={(event) => setAsOf(event.target.value)}
          />
          <span className="mt-1 block text-xs text-[var(--text-secondary)]">
            The window ends here. Leave empty to use the latest GA4 data.
          </span>
        </FieldLabel>

        <FieldLabel label="Lookback">
          <Select
            value={String(lookbackDays)}
            onChange={(event) => setLookbackDays(Number(event.target.value))}
          >
            {LOOKBACK_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </FieldLabel>

        <button
          type="button"
          className="btn btn-secondary"
          disabled={pending}
          onClick={() => {
            setError(null);
            setMessage(null);
            startTransition(async () => {
              const result = await previewBaselineFromGa4Action(clientId, {
                asOf: asOf || null,
                lookbackDays,
              });
              if (!result.ok) {
                setError(result.error);
                setPreview(null);
                return;
              }
              setPreview(result.preview);
              setGoal(String(result.preview.suggested_monthly_lead_goal));
            });
          }}
        >
          {pending && !preview ? "Loading…" : savedProjection ? "Re-run" : "Build"}
        </button>
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}

      {preview ? (
        <div className="space-y-4 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4">
          <div className="grid gap-3 sm:grid-cols-4 text-sm">
            <div>
              <div className="text-xs text-[var(--text-tertiary)]">Window</div>
              <div className="font-medium">
                {preview.window.from} → {preview.window.to}
              </div>
              <div className="text-xs text-[var(--text-secondary)]">
                {preview.window.period_days}d → monthly
              </div>
              {!preview.window.fully_covered ? (
                <div className="mt-1 text-xs font-semibold text-[var(--warning)]">
                  Only {preview.window.period_days} of {preview.window.requested_days}{" "}
                  requested days have GA4 facts
                </div>
              ) : null}
            </div>
            <div>
              <div className="text-xs text-[var(--text-tertiary)]">Monthly sessions</div>
              <div className="font-medium">{formatNum(preview.baseline_monthly_sessions)}</div>
            </div>
            <div>
              <div className="text-xs text-[var(--text-tertiary)]">Monthly leads</div>
              <div className="font-medium">{formatNum(preview.baseline_monthly_leads)}</div>
            </div>
            <div>
              <div className="text-xs text-[var(--text-tertiary)]">Lead rate</div>
              <div className="font-medium">
                {preview.baseline_lead_rate_pct != null
                  ? `${preview.baseline_lead_rate_pct.toFixed(2)}%`
                  : "—"}
              </div>
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]">
              {preview.plan_label} projection
            </p>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[420px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-left text-xs text-[var(--text-tertiary)]">
                    <th className="py-1.5 pr-2 font-semibold">Checkpoint</th>
                    <th className="py-1.5 pr-2 font-semibold">Lead rate</th>
                    <th className="py-1.5 font-semibold">Leads/mo</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.checkpoints.map((row) => (
                    <tr key={row.month} className="border-b border-[var(--border)]">
                      <td className="py-1.5 pr-2">{row.label}</td>
                      <td className="py-1.5 pr-2">{row.lead_rate_pct.toFixed(2)}%</td>
                      <td className="py-1.5 font-medium">
                        {formatNum(Math.round(row.monthly_leads))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <FieldLabel label="Monthly lead goal (editable)">
              <Input
                type="number"
                min={0}
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
              />
              <span className="mt-1 block text-xs text-[var(--text-secondary)]">
                Suggested from {preview.plan_label} 12‑month projection:{" "}
                {formatNum(preview.suggested_monthly_lead_goal)}
              </span>
            </FieldLabel>
            <button
              type="button"
              className="btn btn-primary"
              disabled={pending}
              onClick={() => {
                setError(null);
                setMessage(null);
                const formData = new FormData();
                formData.set("clientId", clientId);
                formData.set("monthly_lead_goal", goal);
                formData.set("as_of", preview.baseline_as_of);
                formData.set("lookback_days", String(preview.window.requested_days));
                startTransition(async () => {
                  const result = await applyBaselineFromGa4Action(formData);
                  if (!result.ok) {
                    setError(result.error);
                    return;
                  }
                  setPreview(result.preview);
                  setMessage(
                    `Baseline saved. Monthly lead goal set to ${formatNum(
                      result.preview.applied_monthly_lead_goal ??
                        result.preview.suggested_monthly_lead_goal,
                    )}.`,
                  );
                  router.refresh();
                });
              }}
            >
              {pending ? "Saving…" : "Freeze snapshot + projection"}
            </button>
          </div>

          <p className="text-xs text-[var(--text-tertiary)]">{preview.disclaimer}</p>
        </div>
      ) : null}
    </div>
  );
}
