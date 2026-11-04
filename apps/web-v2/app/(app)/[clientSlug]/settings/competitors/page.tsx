import { notFound } from "next/navigation";

import { CompetitorsForm } from "@/components/ClientForms";
import { getClients } from "@/lib/clients";

export const metadata = { title: "Settings · Competitors" };

export default async function CompetitorsPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();
  return <CompetitorsForm client={client} />;
}
