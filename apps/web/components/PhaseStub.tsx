export function PhaseStub({ title, description }: { title: string; description: string }) {
  return (
    <section className="card-elevated p-8">
      <p className="badge badge-neutral w-fit">Coming soon</p>
      <h1 className="page-title mt-4">{title}</h1>
      <p className="page-description">{description}</p>
      <p className="mt-6 text-xs uppercase tracking-[0.16em] text-[var(--muted)]">
        No placeholder metrics — unavailable means unavailable
      </p>
    </section>
  );
}
