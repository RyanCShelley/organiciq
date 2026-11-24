import { notFound } from "next/navigation";

import { BaselineBuilder } from "@/components/BaselineBuilder";
import type { SetupState } from "@/components/SetupChecklist";
import { apiFetch } from "@/lib/api";
import type { BaselineEventsResponse, BaselineVersion } from "@/lib/baseline";
import { getClients } from "@/lib/clients";
import type { ConversionDefinition } from "@/lib/conversions";

export const metadata = { title: "Settings · Baseline & goals" };

export default async function BaselinePage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  const [definitions, versions, eventsInfo, setup] = await Promise.all([
    apiFetch<(ConversionDefinition & { id: string })[]>("/admin/conversion-definitions", { clientId: client.id }),
    apiFetch<BaselineVersion[]>(`/clients/${client.id}/baseline/versions`),
    apiFetch<BaselineEventsResponse>(`/clients/${client.id}/baseline/events`).catch(() => null),
    apiFetch<SetupState>(`/clients/${client.id}/setup`).catch(() => null),
  ]);
  const activeNonEngagement = definitions.filter((d) => d.active && d.conversion_type !== "engagement");
  const ecommerceDefs = activeNonEngagement.filter((d) =>
    ["ecommerce", "purchase", "order"].includes(d.conversion_type.toLowerCase()),
  );
  const leadOrCallDefs = activeNonEngagement.filter((d) =>
    ["lead", "call"].includes(d.conversion_type.toLowerCase()),
  );
  const bm = (client.business_model ?? "").toLowerCase();
  const counted =
    bm === "ecommerce"
      ? ecommerceDefs.length > 0
        ? ecommerceDefs
        : leadOrCallDefs
      : bm === "both"
        ? activeNonEngagement
        : leadOrCallDefs;

  return (
    <BaselineBuilder
      clientId={client.id}
      slug={client.slug}
      model={client.business_model ?? null}
      counted={counted.map((d) => ({ event: d.event_name, type: d.conversion_type }))}
      defaultLeadEvents={eventsInfo?.defaults ?? counted.map((d) => d.event_name)}
      versions={versions}
      currentGoal={eventsInfo?.goal.current ?? client.monthly_lead_goal ?? null}
      goalState={eventsInfo?.goal ?? null}
      setup={setup}
    />
  );
}
