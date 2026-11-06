import { notFound } from "next/navigation";

import { PlanBanner } from "@/components/PlanBanner";
import { ContentRefreshes } from "@/components/ContentRefreshes";
import { ApiError, apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import type { Refreshes } from "@/lib/content";

export const metadata = { title: "Content refreshes" };

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

/** The twelve complete months, newest first. */
function lastMonths(): string[] {
  const out: string[] = [];
  const now = new Date();
  for (let i = 1; i <= 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return out;
}

export default async function ContentRefreshesPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<{ month?: string; q?: string; ignored?: string }>;
}) {
  const { clientSlug } = await params;
  const { month: asked, q, ignored } = await searchParams;
  const client = await findClient(clientSlug);
  if (!client) notFound();

  const months = lastMonths();
  const month = asked && MONTH.test(asked) ? asked : months[0];
  let data: Refreshes | null = null;
  let error: string | null = null;
  try {
    const query = new URLSearchParams({ month });
    if (q?.trim()) query.set("q", q.trim());
    if (ignored) query.set("ignored", "true");
    data = await apiFetch<Refreshes>(`/v2/content/refreshes?${query}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The content refreshes could not be built: the API did not answer.";
  }
  return (
    <>
      <PlanBanner doing="Plan the refresh for this page." />
      <ContentRefreshes client={client} month={month} months={months.includes(month) ? months : [month, ...months]} q={q?.trim() ?? ""} ignored={!!ignored} data={data} error={error} />
    </>
  );
}
