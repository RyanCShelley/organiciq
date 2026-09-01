export function PhaseStub({ title, description }: { title: string; description: string }) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-8">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-3 max-w-2xl text-sm text-[var(--muted)]">{description}</p>
      <p className="mt-6 text-xs uppercase tracking-wide text-[var(--muted)]">
        No placeholder metrics — unavailable means unavailable
      </p>
    </section>
  );
}
