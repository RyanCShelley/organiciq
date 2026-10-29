import { notFound } from "next/navigation";

import { GeneralForm } from "@/components/ClientForms";
import { getClients, getTiers } from "@/lib/clients";

export const metadata = { title: "Settings · General" };

export default async function GeneralPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const [clients, tiers] = await Promise.all([getClients(), getTiers()]);
  const client = clients.find((c) => c.slug === clientSlug);
  if (!client) notFound();
  return <GeneralForm client={client} tiers={tiers} />;
}
