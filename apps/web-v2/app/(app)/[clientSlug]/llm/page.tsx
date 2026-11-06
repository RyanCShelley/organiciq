import { notFound } from "next/navigation";

import { LlmScreen } from "@/components/LlmScreen";
import { ApiError, apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import type { LlmOverview, LlmSettings } from "@/lib/llm";

export const metadata = { title: "LLM visibility" };

export default async function LlmPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<{ run?: string }>;
}) {
  const { clientSlug } = await params;
  const { run } = await searchParams;
  const client = await findClient(clientSlug);
  if (!client) notFound();

  let overview: LlmOverview | null = null;
  let error: string | null = null;
  try {
    const query = run && /^[0-9a-f-]{36}$/i.test(run) ? `?run_id=${run}` : "";
    overview = await apiFetch<LlmOverview>(`/v2/llm/overview${query}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "LLM visibility could not be loaded: the API did not answer.";
  }
  const settings = await apiFetch<LlmSettings>("/v2/llm/settings", { clientId: client.id }).catch(() => null);

  return (
    <>
      <LlmScreen client={client} overview={overview} settings={settings} error={error} />
    </>
  );
}
