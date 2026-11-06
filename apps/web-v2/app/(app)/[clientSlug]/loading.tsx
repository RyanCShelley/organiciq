/**
 * Shown the instant a screen is chosen, while its data is read.
 *
 * Without it the old screen stayed in place until the new one was ready, so a click seemed to do nothing. Screens with their own
 * loading.tsx (the monthly review) keep theirs. The shape is a heading, a line of text and a few blocks: no screen is promised.
 */
export default function Loading() {
  return (
    <section className="max-w-6xl animate-pulse" aria-busy="true" aria-label="Loading">
      <div className="h-7 w-64 rounded bg-[var(--border)]" />
      <div className="mt-3 h-4 w-[28rem] max-w-full rounded bg-[var(--border)]" />
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-24 rounded-lg border border-[var(--border)] bg-white" />
        ))}
      </div>
      <div className="mt-6 space-y-3">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="h-12 rounded-lg border border-[var(--border)] bg-white" />
        ))}
      </div>
    </section>
  );
}
