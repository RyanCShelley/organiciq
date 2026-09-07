"use client";

import { useState, useTransition } from "react";

import { updateClientSettingsAction } from "@/app/(app)/actions";
import { BaselineSnapshotPanel } from "@/components/BaselineSnapshotPanel";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { FieldLabel, Input, Select } from "@/components/ui/Input";
import type { Client, Tier } from "@/lib/api";
import { isEnterpriseTier, resolvePlanAllowances } from "@/lib/plan-allowances";

const STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "onboarding", label: "Onboarding" },
  { value: "paused", label: "Paused" },
  { value: "archived", label: "Archived" },
];

const CADENCE_OPTIONS = [
  { value: "monthly", label: "Monthly" },
  { value: "bi_weekly", label: "Bi-weekly" },
  { value: "weekly", label: "Weekly" },
];

function formatCadence(cadence?: string | null): string {
  switch (cadence) {
    case "weekly":
      return "weekly";
    case "bi_weekly":
      return "bi-weekly";
    case "monthly":
    case undefined:
    case null:
    case "":
      return "monthly";
    default:
      return cadence.replaceAll("_", "-");
  }
}

export function ClientSettingsForm({
  client,
  tiers,
  hasLeadConversions = false,
}: {
  client: Client;
  tiers: Tier[];
  hasLeadConversions?: boolean;
}) {
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tierId, setTierId] = useState(client.tier_id);
  const selectedTier = tiers.find((tier) => tier.id === tierId) ?? tiers[0];
  const enterprise = isEnterpriseTier(selectedTier);
  const allowances = resolvePlanAllowances(client, selectedTier);

  return (
    <form
      className="space-y-5"
      action={(formData) => {
        setMessage(null);
        setError(null);
        startTransition(async () => {
          const result = await updateClientSettingsAction(formData);
          if (result.ok) setMessage("Client settings saved.");
          else setError(result.error);
        });
      }}
    >
      <input type="hidden" name="clientId" value={client.id} />
      <input type="hidden" name="is_enterprise" value={enterprise ? "1" : "0"} />

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <FieldLabel label="Company name">
          <Input name="client_name" defaultValue={client.client_name} required />
        </FieldLabel>
        <FieldLabel label="Website URL / domain">
          <Input name="domain" defaultValue={client.domain} required />
        </FieldLabel>
        <FieldLabel label="OrganicIQ tier">
          <Select
            name="tier_id"
            value={tierId}
            required
            onChange={(event) => setTierId(event.target.value)}
          >
            {tiers.map((tier) => (
              <option key={tier.id} value={tier.id}>
                {tier.tier_name}
              </option>
            ))}
          </Select>
        </FieldLabel>
        <FieldLabel label="Status">
          <Select name="status" defaultValue={client.status}>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </FieldLabel>
        <FieldLabel label="Contract start date">
          <Input name="start_date" type="date" defaultValue={client.start_date ?? ""} />
        </FieldLabel>
        <FieldLabel label="Monthly lead goal">
          <Input
            name="monthly_lead_goal"
            type="number"
            min={0}
            defaultValue={client.monthly_lead_goal ?? ""}
            placeholder="From growth calculator"
          />
        </FieldLabel>
        <FieldLabel label="Primary market">
          <Input name="primary_market" defaultValue={client.primary_market ?? ""} />
        </FieldLabel>
        <FieldLabel label="Timezone">
          <Input name="timezone" defaultValue={client.timezone} />
        </FieldLabel>
      </div>

      <FieldLabel label="Google Sheet account record">
        <Input
          name="account_sheet_url"
          type="url"
          defaultValue={client.account_sheet_url ?? ""}
          placeholder="https://docs.google.com/spreadsheets/..."
        />
      </FieldLabel>

      <div className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-muted)] p-4 space-y-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]">
            Dashboard baseline snapshot
          </p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Freeze starting monthly sessions, leads, and lead rate (from the growth calculator or
            kickoff numbers). Dashboard compares the current window against this snapshot.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <FieldLabel label="Baseline as of">
            <Input
              name="baseline_as_of"
              type="date"
              defaultValue={client.baseline_as_of ?? ""}
            />
          </FieldLabel>
          <FieldLabel label="Monthly sessions">
            <Input
              name="baseline_monthly_sessions"
              type="number"
              min={0}
              defaultValue={client.baseline_monthly_sessions ?? ""}
              placeholder="From calculator"
            />
          </FieldLabel>
          <FieldLabel label="Monthly leads">
            <Input
              name="baseline_monthly_leads"
              type="number"
              min={0}
              defaultValue={client.baseline_monthly_leads ?? ""}
            />
          </FieldLabel>
          <FieldLabel label="Lead rate %">
            <Input
              name="baseline_lead_rate_pct"
              type="number"
              min={0}
              step="0.01"
              defaultValue={client.baseline_lead_rate_pct ?? ""}
              placeholder="Auto from leads ÷ sessions"
            />
          </FieldLabel>
          <FieldLabel label="Source">
            <Select name="baseline_source" defaultValue={client.baseline_source ?? "manual"}>
              <option value="manual">Manual</option>
              <option value="ga4_calculator">GA4 + calculator</option>
              <option value="calculator">Growth calculator</option>
              <option value="ga4">GA4 snapshot</option>
              <option value="kickoff">Kickoff / audit</option>
            </Select>
          </FieldLabel>
          <FieldLabel label="Notes" className="sm:col-span-2 lg:col-span-1">
            <Input
              name="baseline_notes"
              defaultValue={client.baseline_notes ?? ""}
              placeholder="e.g. Pre-engagement July 2025"
            />
          </FieldLabel>
        </div>
        <BaselineSnapshotPanel clientId={client.id} hasLeadConversions={hasLeadConversions} />
      </div>

      {selectedTier && !enterprise ? (
        <div className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-muted)] p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]">
            {selectedTier.tier_name} plan allowances
          </p>
          <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-xs text-[var(--text-tertiary)]">Watchlist</dt>
              <dd className="text-sm font-semibold">
                {allowances.trackedKeywordLimit} keywords + AI prompts
              </dd>
              <dd className="text-xs text-[var(--text-secondary)]">
                Checked {formatCadence(allowances.watchlistCadence)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--text-tertiary)]">New content</dt>
              <dd className="text-sm font-semibold">{allowances.contentAllowance} per quarter</dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--text-tertiary)]">Content refresh</dt>
              <dd className="text-sm font-semibold">{allowances.updateAllowance} per quarter</dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--text-tertiary)]">Growth Actions</dt>
              <dd className="text-sm font-semibold">
                {allowances.growthActionAllowance} per month
              </dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-[var(--text-secondary)]">
            Decision Engine uses the monthly Growth Action allowance as a plan floor for how many
            recommendations to surface — without changing scores.
          </p>
        </div>
      ) : null}

      {enterprise ? (
        <div className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-muted)] p-4 space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]">
              Enterprise custom allowances
            </p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Set agreement-specific amounts for this client. These override the catalog and drive
              Watch List limits and the Decision Engine plan floor.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <FieldLabel label="Watchlist (keywords + AI prompts)">
              <Input
                name="custom_tracked_keyword_limit"
                type="number"
                min={0}
                required
                defaultValue={
                  client.custom_tracked_keyword_limit ??
                  (allowances.trackedKeywordLimit || "")
                }
              />
            </FieldLabel>
            <FieldLabel label="Watchlist cadence">
              <Select
                name="custom_watchlist_cadence"
                defaultValue={client.custom_watchlist_cadence ?? allowances.watchlistCadence}
              >
                {CADENCE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </FieldLabel>
            <FieldLabel label="New content per quarter">
              <Input
                name="custom_content_allowance"
                type="number"
                min={0}
                required
                defaultValue={
                  client.custom_content_allowance ?? (allowances.contentAllowance || "")
                }
              />
            </FieldLabel>
            <FieldLabel label="Content refresh per quarter">
              <Input
                name="custom_update_allowance"
                type="number"
                min={0}
                required
                defaultValue={
                  client.custom_update_allowance ?? (allowances.updateAllowance || "")
                }
              />
            </FieldLabel>
            <FieldLabel label="Growth Actions per month">
              <Input
                name="custom_growth_action_allowance"
                type="number"
                min={0}
                required
                defaultValue={
                  client.custom_growth_action_allowance ??
                  (allowances.growthActionAllowance || "")
                }
              />
            </FieldLabel>
          </div>
        </div>
      ) : null}

      <Button type="submit" variant="primary" disabled={pending}>
        {pending ? "Saving…" : "Save client settings"}
      </Button>
    </form>
  );
}
