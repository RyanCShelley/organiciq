import { notFound, redirect } from "next/navigation";

import { findClient } from "@/lib/clients";

/** A client's home is the monthly review. */
export default async function ClientHomePage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = await findClient(clientSlug);
  if (!client) notFound();
  redirect(`/${client.slug}/review`);
}
