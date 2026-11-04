import Link from "next/link";
import { notFound } from "next/navigation";

import { BaselineBuilder } from "@/components/BaselineBuilder";
import { apiFetch } from "@/lib/api";
import type { BaselineVersion } from "@/lib/baseline";
import { getClients } from "@/lib/clients";
import type { ConversionDefinition } from "@/lib/conversions";

export const metadata = { title: "Settings · Baseline & goals" };

export default async function BaselinePage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  const [definitions, versions] = await Promise.all([
    apiFetch<(ConversionDefinition & { id: string })[]>("/admin/conversion-definitions", { clientId: client.id }),
    apiFetch<BaselineVersion[]>(`/clients/${client.id}/baseline/versions`),
  ]);
  const counted = definitions.filter((d) => d.active && d.conversion_type !== "engagement");

  if (counted.length === 0) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-sm">
        <h2 className="font-semibold">Choose what counts first</h2>
        <p className="mt-1 text-[var(--text-secondary)]">
          A baseline counts conversions, so it needs to know which GA4 events they are. Pick them on{" "}
          <Link href={`/${client.slug}/settings/conversions`} className="font-semibold text-[var(--brand-teal)] hover:underline">
            Conversions &amp; goals
          </Link>
          , then come back.
        </p>
      </div>
    );
  }

  return (
    <BaselineBuilder
      clientId={client.id}
      slug={client.slug}
      model={client.business_model ?? null}
      counted={counted.map((d) => ({ event: d.event_name, type: d.conversion_type }))}
      versions={versions}
      currentGoal={client.monthly_lead_goal ?? null}
    />
  );
}
