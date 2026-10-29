"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { clearFocusAction, saveFocusAction } from "@/app/(app)/[clientSlug]/focus/actions";
import { FOCUSES, type ClientFocus, type FocusValue, monthLabel } from "@/lib/focus";
import type { WatchlistBucket } from "@/lib/watchlist";

export function FocusForm({
  clientId,
  slug,
  month,
  current,
  buckets,
}: {
  clientId: string;
  slug: string;
  month: string;
  current: ClientFocus | null;
  buckets: Pick<WatchlistBucket, "id" | "name">[];
}) {
  const router = useRouter();
  const [focus, setFocus] = useState<FocusValue | null>(current?.focus ?? null);
  const [bucketId, setBucketId] = useState(current?.bucket_id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, startTransition] = useTransition();

  function save() {
    if (!focus) return;
    setError(null);
    setSaved(false);
    startTransition(async () => {
      const result = await saveFocusAction(clientId, slug, month, focus, bucketId || null);
      if (result.ok) setSaved(true);
      else setError(result.error);
    });
  }

  function clear() {
    setError(null);
    setSaved(false);
    startTransition(async () => {
      const result = await clearFocusAction(clientId, slug, month);
      if (result.ok) {
        setFocus(null);
        setBucketId("");
      } else setError(result.error);
    });
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-sm font-semibold">Focus for {monthLabel(month)}</h2>
        <input
          type="month"
          value={month}
          aria-label="Month"
          onChange={(event) => {
            if (event.target.value) router.push(`/${slug}/focus?month=${event.target.value}`);
          }}
          className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm"
        />
      </div>

      <fieldset className="mt-4">
        <legend className="sr-only">Focus</legend>
        <div className="grid gap-3 sm:grid-cols-3">
          {FOCUSES.map((option) => (
            <label
              key={option.value}
              className={`cursor-pointer rounded-lg border p-4 text-sm ${
                focus === option.value
                  ? "border-[var(--brand-teal)] bg-[var(--brand-teal)]/10"
                  : "border-[var(--border)] hover:border-[var(--brand-teal)]"
              }`}
            >
              <input
                type="radio"
                name="focus"
                value={option.value}
                checked={focus === option.value}
                onChange={() => {
                  setFocus(option.value);
                  setSaved(false);
                }}
                className="sr-only"
              />
              <span className="block font-semibold">{option.label}</span>
              <span className="mt-1 block text-[var(--text-secondary)]">{option.hint}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <label className="mt-4 block text-sm">
        <span className="font-semibold">Watchlist bucket</span>
        <select
          value={bucketId}
          onChange={(event) => {
            setBucketId(event.target.value);
            setSaved(false);
          }}
          className="mt-1 block w-full rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
        >
          <option value="">{buckets.length ? "No bucket chosen" : "No buckets yet: import the watchlist first"}</option>
          {buckets.map((bucket) => (
            <option key={bucket.id} value={bucket.id}>
              {bucket.name}
            </option>
          ))}
        </select>
      </label>

      <div className="mt-5 flex items-center gap-3">
        <button
          type="button"
          disabled={pending || !focus}
          onClick={save}
          className="rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          Save focus
        </button>
        {current ? (
          <button
            type="button"
            disabled={pending}
            onClick={clear}
            className="text-sm font-semibold text-red-700 hover:underline disabled:opacity-50"
          >
            Clear
          </button>
        ) : null}
        {saved ? <span className="text-sm text-[var(--text-secondary)]">Saved.</span> : null}
      </div>

      {error ? (
        <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      ) : null}
    </div>
  );
}
