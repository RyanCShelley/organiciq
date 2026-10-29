import Link from "next/link";
import { notFound } from "next/navigation";

import { V2_SECTIONS } from "@/components/layout/V2Shell";
import { getClients } from "@/lib/clients";

export default async function ClientHomePage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const clients = await getClients();
  const client = clients.find((c) => c.slug === clientSlug);
  if (!client) notFound();

  return (
    <section className="max-w-2xl">
      <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">
        {client.client_name}
      </h1>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        {client.domain}
        {client.plan_label ? ` · ${client.plan_label}` : ""}
      </p>

      <Link
        href={`/${client.slug}/watchlist`}
        className="mt-8 block rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-sm font-semibold hover:border-[var(--brand-teal)]"
      >
        Watchlist →
      </Link>
      <Link
        href={`/${client.slug}/settings`}
        className="mt-3 block rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-sm font-semibold hover:border-[var(--brand-teal)]"
      >
        Settings →
      </Link>

      <div className="mt-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
        <h2 className="text-sm font-semibold">What is coming to v2</h2>
        <ol className="mt-3 space-y-2 text-sm text-[var(--text-secondary)]">
          {V2_SECTIONS.map((section) => (
            <li key={section.label} className="flex justify-between">
              <span>{section.label}</span>
              <span className="text-[var(--text-tertiary)]">{section.phase}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
