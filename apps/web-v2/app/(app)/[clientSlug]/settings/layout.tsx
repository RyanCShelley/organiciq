import { notFound } from "next/navigation";

import { SettingsTabs } from "@/components/layout/SettingsTabs";
import { getClients } from "@/lib/clients";

export default async function SettingsLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  return (
    <section className="max-w-6xl space-y-6">
      <header>
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">{client.client_name}</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">{client.domain} · Settings</p>
      </header>
      <SettingsTabs />
      <div className="max-w-4xl">{children}</div>
    </section>
  );
}
