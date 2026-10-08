"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";

export type ConversionPage = {
  id?: string;
  normalized_url: string;
  label: string;
  stage: string | null;
  is_primary: boolean;
};

const STAGES = [
  { value: "", label: "Any stage" },
  { value: "tofu", label: "Early — just learning" },
  { value: "mofu", label: "Comparing options" },
  { value: "bofu", label: "Ready to buy" },
];

function blank(): ConversionPage {
  return { normalized_url: "", label: "", stage: null, is_primary: false };
}

/**
 * Where a visitor is meant to end up, named by the person who knows.
 *
 * Without this the engine guesses from URL fragments — /contact, /demo,
 * /quote. ACCTek's offer is /contact-us, so every conversion action told
 * the team to add links to /contact, which 404s. The guess stays as the
 * fallback; a declared page overrides it.
 */
export function ConversionPagesPanel({
  clientId,
  initial,
}: {
  clientId: string;
  initial: ConversionPage[];
}) {
  const router = useRouter();
  const [rows, setRows] = useState<ConversionPage[]>(
    initial.length > 0 ? initial : [blank()],
  );
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  function update(index: number, patch: Partial<ConversionPage>) {
    setSaved(false);
    setRows((current) =>
      current.map((row, i) => {
        if (i !== index) {
          // One primary at most: the engine falls back to it when a page's
          // stage matches nothing, so two is a silent coin toss.
          return patch.is_primary ? { ...row, is_primary: false } : row;
        }
        return { ...row, ...patch };
      }),
    );
  }

  function save() {
    setError(null);
    setSaved(false);
    const pages = rows
      .filter((row) => row.normalized_url.trim() && row.label.trim())
      .map((row) => ({
        normalized_url: row.normalized_url.trim(),
        label: row.label.trim(),
        stage: row.stage || null,
        is_primary: row.is_primary,
      }));

    startTransition(async () => {
      const res = await fetch("/api/proxy/conversion-pages", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId, pages }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setError(body?.detail ?? "Could not save");
        return;
      }
      setSaved(true);
      router.refresh();
    });
  }

  return (
    <div className="space-y-4">
      {error ? <Alert variant="danger">{error}</Alert> : null}
      {saved ? (
        <Alert variant="success">
          Saved. The next run will send people to these pages instead of guessing.
        </Alert>
      ) : null}

      <div className="space-y-3">
        {rows.map((row, index) => (
          <div
            key={index}
            className="grid gap-3 rounded-lg border border-[var(--border)] p-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_auto]"
          >
            <label className="block">
              <span className="mb-1 block text-xs text-[var(--text-tertiary)]">Page URL</span>
              <Input
                value={row.normalized_url}
                placeholder="https://example.com/contact-us"
                onChange={(e) => update(index, { normalized_url: e.target.value })}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-[var(--text-tertiary)]">
                What to call it
              </span>
              <Input
                value={row.label}
                placeholder="Contact"
                onChange={(e) => update(index, { label: e.target.value })}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-[var(--text-tertiary)]">
                Who it&rsquo;s for
              </span>
              <Select
                value={row.stage ?? ""}
                onChange={(e) => update(index, { stage: e.target.value || null })}
              >
                {STAGES.map((stage) => (
                  <option key={stage.value} value={stage.value}>
                    {stage.label}
                  </option>
                ))}
              </Select>
            </label>
            <div className="flex items-end gap-3 pb-1">
              <label className="flex items-center gap-2 text-[13px] text-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  checked={row.is_primary}
                  onChange={(e) => update(index, { is_primary: e.target.checked })}
                />
                Main
              </label>
              <button
                type="button"
                aria-label="Remove this page"
                className="min-h-[44px] px-2 text-[13px] text-[var(--text-tertiary)] hover:text-[var(--danger)]"
                onClick={() => {
                  setSaved(false);
                  setRows((c) => (c.length === 1 ? [blank()] : c.filter((_, i) => i !== index)));
                }}
              >
                Remove
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            setSaved(false);
            setRows((c) => [...c, blank()]);
          }}
        >
          Add a page
        </Button>
        <Button type="button" onClick={save} disabled={pending}>
          {pending ? "Saving…" : "Save conversion pages"}
        </Button>
      </div>
    </div>
  );
}
