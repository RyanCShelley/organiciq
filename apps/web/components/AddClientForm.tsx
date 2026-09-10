"use client";

import { Plus, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { createClientAction } from "@/app/(app)/client-actions";
import { Alert } from "@/components/ui/Alert";
import { FieldLabel, Input, Select } from "@/components/ui/Input";
import type { Tier } from "@/lib/api";

const STATUS_OPTIONS = [
  { value: "onboarding", label: "Onboarding" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
];

export function AddClientForm({ tiers }: { tiers: Tier[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const noTiers = tiers.length === 0;

  if (!open) {
    return (
      <button
        type="button"
        className="btn btn-primary gap-2"
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
      >
        <Plus className="h-3.5 w-3.5" aria-hidden />
        Add client
      </button>
    );
  }

  return (
    <div className="card w-full p-[var(--card-padding-lg)]">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="section-title">Add client</h2>
          <p className="mt-1 text-[12.5px] text-[var(--text-tertiary)]">
            Name, domain and tier are required. Everything else is editable in Client
            settings once the workspace exists.
          </p>
        </div>
        <button
          type="button"
          aria-label="Cancel"
          className="btn btn-ghost btn-sm"
          onClick={() => setOpen(false)}
          disabled={pending}
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>

      {noTiers ? (
        <Alert variant="warning">
          No tiers are configured yet, so a client cannot be created. Add one in Platform →
          Settings first.
        </Alert>
      ) : null}

      {error ? (
        <Alert variant="danger" className="mb-3">
          {error}
        </Alert>
      ) : null}

      <form
        action={(formData) => {
          setError(null);
          startTransition(async () => {
            const result = await createClientAction(formData);
            if (!result.ok) {
              setError(result.error);
              return;
            }
            setOpen(false);
            // Land in the new workspace — integrations are the next step.
            router.push(`/clients/${result.slug}/integrations`);
            router.refresh();
          });
        }}
        className="grid gap-3 sm:grid-cols-2"
      >
        <FieldLabel label="Client name">
          <Input name="client_name" required placeholder="Acme Manufacturing" autoFocus />
        </FieldLabel>

        <FieldLabel label="Domain">
          <Input name="domain" required placeholder="acme.com" inputMode="url" />
        </FieldLabel>

        <FieldLabel label="Tier">
          <Select name="tier_id" required defaultValue={tiers[0]?.id ?? ""}>
            {tiers.map((tier) => (
              <option key={tier.id} value={tier.id}>
                {tier.tier_name}
              </option>
            ))}
          </Select>
        </FieldLabel>

        <FieldLabel label="Status">
          <Select name="status" defaultValue="onboarding">
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </FieldLabel>

        <FieldLabel label="Monthly lead goal (optional)">
          <Input name="monthly_lead_goal" type="number" min={0} placeholder="31" />
        </FieldLabel>

        <FieldLabel label="Start date (optional)">
          <Input name="start_date" type="date" />
        </FieldLabel>

        <div className="flex items-center gap-2 sm:col-span-2">
          <button type="submit" className="btn btn-primary" disabled={pending || noTiers}>
            {pending ? "Creating…" : "Create client"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setOpen(false)}
            disabled={pending}
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
