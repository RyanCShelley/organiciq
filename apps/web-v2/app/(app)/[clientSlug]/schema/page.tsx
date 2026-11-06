import { notFound } from "next/navigation";

import { PlanBanner } from "@/components/PlanBanner";
import { SchemaScreen } from "@/components/SchemaScreen";
import { ApiError, apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import type { ScResponse } from "@/lib/schema";

export const metadata = { title: "Machine readability" };

export default async function SchemaPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = await findClient(clientSlug);
  if (!client) notFound();

  let result: ScResponse | null = null;
  let error: string | null = null;
  try {
    result = await apiFetch<ScResponse>("/v2/schema", { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "Schema could not be read: the API did not answer.";
  }
  return (
    <>
      <PlanBanner doing="Write the markup this page needs." />
      <SchemaScreen client={client} result={result} error={error} />
    </>
  );
}
