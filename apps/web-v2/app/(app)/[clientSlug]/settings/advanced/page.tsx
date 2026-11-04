import { notFound } from "next/navigation";

import { AdvancedForm } from "@/components/ClientForms";
import { getClients } from "@/lib/clients";

export const metadata = { title: "Settings · Advanced" };

export default async function AdvancedPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();
  return <AdvancedForm client={client} />;
}
