"use client";

import Link from "next/link";

export default function ClientRouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const msg = error?.message || "This client screen could not be opened.";
  const isForbidden = /403|forbidden|staff|not authorized|only sma/i.test(msg);

  return (
    <section className="mx-auto max-w-2xl space-y-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
      <h1 className="font-[family-name:var(--font-display)] text-xl font-bold text-[var(--text-primary)]">
        {isForbidden ? "Access restricted" : "Could not load this client page"}
      </h1>
      <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">
        {isForbidden
          ? "Only authorized SMA staff can view this client workspace."
          : msg}
      </p>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <Link
          href="/"
          className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 font-semibold text-white"
        >
          Back to overview
        </Link>
        {!isForbidden ? (
          <button
            type="button"
            onClick={reset}
            className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 font-semibold"
          >
            Try again
          </button>
        ) : null}
      </div>
    </section>
  );
}
