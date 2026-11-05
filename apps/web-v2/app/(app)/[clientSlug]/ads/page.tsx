import { notFound } from "next/navigation";

import { AdsAccelerator } from "@/components/AdsAccelerator";
import { ApiError, apiFetch } from "@/lib/api";
import type { AdsReport } from "@/lib/ads";
import { findClient } from "@/lib/clients";
import { lastCompleteMonth } from "@/lib/review";

export const metadata = { title: "Ads Accelerator" };

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

/** The twelve most recent complete months, newest first. */
function lastMonths(): string[] {
  const out: string[] = [];
  const now = new Date();
  for (let i = 1; i <= 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return out;
}

export default async function AdsPage({ params, searchParams }: { params: Promise<{ clientSlug: string }>; searchParams: Promise<{ month?: string }> }) {
  const { clientSlug } = await params;
  const { month: asked } = await searchParams;
  const client = await findClient(clientSlug);
  if (!client) notFound();
  const months = lastMonths();
  const month = asked && MONTH.test(asked) ? asked : lastCompleteMonth();
  let data: AdsReport | null = null;
  let error: string | null = null;
  try {
    data = await apiFetch<AdsReport>(`/v2/ads?month=${month}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The ads report could not be built: the API did not answer.";
  }
  return <AdsAccelerator client={client} month={month} months={months.includes(month) ? months : [month, ...months]} data={data} error={error} />;
}
