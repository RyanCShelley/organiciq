import { notFound } from "next/navigation";

import { SitemapForm } from "@/components/ClientForms";
import { getClients } from "@/lib/clients";

export const metadata = { title: "Settings · Content sources" };

export default async function ContentSourcesPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();
  return <SitemapForm client={client} />;
}
