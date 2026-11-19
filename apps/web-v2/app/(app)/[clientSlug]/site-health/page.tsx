import { notFound } from "next/navigation";

import { SiteHealth } from "@/components/SiteHealth";
import { ApiError, apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import type { ShResponse } from "@/lib/site-health";

export const metadata = { title: "Site health" };

export default async function SiteHealthPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<{ month?: string; compare_to?: string }>;
}) {
  const { clientSlug } = await params;
  const { month, compare_to } = await searchParams;
  const client = await findClient(clientSlug);
  if (!client) notFound();

  let result: ShResponse | null = null;
  let error: string | null = null;
  try {
    const qs = new URLSearchParams();
    if (month && /^\d{4}-(0[1-9]|1[0-2])$/.test(month)) qs.set("month", month);
    if (compare_to && /^\d{4}-(0[1-9]|1[0-2])$/.test(compare_to)) qs.set("compare_to", compare_to);
    const q = qs.toString() ? `?${qs.toString()}` : "";
    result = await apiFetch<ShResponse>(`/v2/site-health${q}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "Site health could not be read: the API did not answer.";
  }

  return (
    <>
      <SiteHealth client={client} result={result} error={error} />
    </>
  );
}
