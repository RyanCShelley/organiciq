"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { runMonthlyRecordAction } from "@/app/(app)/[clientSlug]/decision-engine/actions";

/**
 * Re-run the current month from the page showing it.
 *
 * States what it will do before it does it. "Run engine" on its own does not
 * say that the saved record is replaced, and the saved record is the thing
 * the whole page renders.
 */
export function RunEngineButton({
  clientId,
  slug,
  month,
}: {
  clientId: string;
  slug: string;
  month: string;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  function run() {
    setError(null);
    startTransition(async () => {
      const result = await runMonthlyRecordAction(clientId, slug);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      // The action revalidates the page; this drops any ?run= pointing at an
      // older month so the reader lands on what was just written.
      router.replace(`/${slug}/decision-engine`);
      router.refresh();
    });
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={run}
        disabled={pending}
        className="inline-flex min-h-[36px] items-center rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3.5 text-[13px] font-semibold text-[var(--text-primary)] disabled:opacity-60"
      >
        {pending ? "Running…" : `Re-run ${month}`}
      </button>
      <p className="text-[11.5px] text-[var(--text-tertiary)]">
        Replaces this month&rsquo;s saved record
      </p>
      {error ? (
        <p role="alert" className="max-w-[40ch] text-right text-[12px] text-[#B4441C]">
          {error}
        </p>
      ) : null}
    </div>
  );
}
