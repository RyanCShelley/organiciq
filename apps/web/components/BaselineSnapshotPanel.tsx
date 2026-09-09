"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  applyBaselineFromGa4Action,
  previewBaselineFromGa4Action,
  type BaselineSnapshotPreview,
} from "@/app/(app)/baseline-actions";
import { Alert } from "@/components/ui/Alert";
import { FieldLabel, Input } from "@/components/ui/Input";

function formatNum(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return Number.isInteger(value)
    ? value.toLocaleString()
    : value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

export function BaselineSnapshotPanel({
  clientId,
  clientSlug,
  hasLeadConversions,
}: {
  clientId: string;
  clientSlug: string;
  hasLeadConversions: boolean;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [preview, setPreview] = useState<BaselineSnapshotPreview | null>(null);
  const [goal, setGoal] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

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
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Create snapshot from GA4
          </p>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            Pulls the last ~30 days of sessions and lead events, scales to monthly, then projects a
            12‑month lead goal from the {preview?.plan_label ?? "tier"} calculator curve.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          disabled={pending}
          onClick={() => {
            setError(null);
            setMessage(null);
            startTransition(async () => {
              const result = await previewBaselineFromGa4Action(clientId);
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
          {pending && !preview ? "Loading…" : "Preview from GA4"}
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
              {pending ? "Saving…" : "Save snapshot + goal"}
            </button>
          </div>

          <p className="text-xs text-[var(--text-tertiary)]">{preview.disclaimer}</p>
        </div>
      ) : null}
    </div>
  );
}
