import { notFound } from "next/navigation";

import { SettingsTabs } from "@/components/layout/SettingsTabs";
import { getClients } from "@/lib/clients";

/** The client's name, the Settings tabs, and the page under them. Every Settings page, and the Watchlist page that sits among them, uses it. */
export async function SettingsFrame({ slug, width = "max-w-4xl", children }: { slug: string; width?: string; children: React.ReactNode }) {
  const client = (await getClients()).find((c) => c.slug === slug);
  if (!client) notFound();

  return (
    <section className="max-w-6xl space-y-6">
      <header>
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">{client.client_name}</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">{client.domain} · Settings</p>
      </header>
      <SettingsTabs />
      <div className={width}>{children}</div>
    </section>
  );
}
