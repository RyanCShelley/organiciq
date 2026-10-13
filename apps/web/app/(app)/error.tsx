"use client";

import Link from "next/link";

/**
 * What a page shows when something it needed failed to load.
 *
 * Without this a failed API call fell through to a bare 404, which sent
 * people looking for a missing page when the real problem was the data
 * service. The message is deliberately generic: Next hides server error text
 * in production, and an error body is not something to print at a reader.
 */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section className="mx-auto max-w-[560px] px-4 py-16">
      <h1 className="font-[family-name:var(--font-display)] text-[22px] font-extrabold text-[var(--text-primary)]">
        This page didn&rsquo;t load
      </h1>
      <p className="mt-2 text-[14px] leading-relaxed text-[var(--text-secondary)]">
        The page exists, but the data behind it didn&rsquo;t come back. That is
        usually temporary. Try again, and if it keeps happening tell whoever
        looks after the API
        {error.digest ? ` and quote ${error.digest}` : ""}.
      </p>
      <div className="mt-5 flex gap-3">
        <button
          type="button"
          onClick={reset}
          className="rounded-[var(--radius-md)] bg-[var(--brand-teal-deep,#0F6B6B)] px-4 py-2 text-[13.5px] font-semibold text-white"
        >
          Try again
        </button>
        <Link
          href="/clients"
          className="rounded-[var(--radius-md)] border border-[var(--border)] px-4 py-2 text-[13.5px] font-semibold text-[var(--text-primary)]"
        >
          All clients
        </Link>
      </div>
    </section>
  );
}
