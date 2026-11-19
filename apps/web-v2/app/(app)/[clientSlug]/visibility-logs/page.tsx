import { notFound } from "next/navigation";

import { VisibilityLogs, type VisibilityLogEntry } from "@/components/VisibilityLogs";
import { ApiError, apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";

export const metadata = { title: "Visibility logs" };

export default async function VisibilityLogsPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = await findClient(clientSlug);
  if (!client) notFound();

  let entries: VisibilityLogEntry[] = [];
  let error: string | null = null;
  try {
    const res = await apiFetch<{ entries: VisibilityLogEntry[] }>("/v2/annotations", { clientId: client.id });
    entries = (res.entries ?? []).filter((e) => e.type === "visibility_check");
  } catch (e) {
    error = e instanceof ApiError ? e.message : "Visibility logs could not be loaded: the API did not answer.";
  }

  return <VisibilityLogs client={client} initialEntries={entries} error={error} />;
}
