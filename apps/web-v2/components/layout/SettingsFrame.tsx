import { notFound } from "next/navigation";

import { SetupBanner, SetupHeaderPill, type SetupState } from "@/components/SetupChecklist";
import { SettingsTabs } from "@/components/layout/SettingsTabs";
import { apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";

/** The client's name, the Settings tabs, and the page under them. Every Settings page, and the Watchlist page that sits among them, uses it. */
export async function SettingsFrame({ slug, width = "max-w-4xl", children }: { slug: string; width?: string; children: React.ReactNode }) {
  const client = (await getClients()).find((c) => c.slug === slug);
  if (!client) notFound();

  const setup = await apiFetch<SetupState>(`/clients/${client.id}/setup`).catch(() => null);

  return (
    <section className="max-w-6xl space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">{client.client_name}</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {client.domain} · Settings
            {client.service_mode === "consulting" ? " · Consulting" : ""}
          </p>
        </div>
        {setup ? <SetupHeaderPill slug={slug} setup={setup} /> : null}
      </header>
      <SettingsTabs setup={setup} />
      {setup ? (
        <SetupBanner
          clientId={client.id}
          slug={slug}
          setup={setup}
          serviceMode={client.service_mode ?? "execution"}
        />
      ) : null}
      <div className={width}>{children}</div>
    </section>
  );
}
