import { notFound } from "next/navigation";

import { ReportEditor } from "@/components/ReportEditor";
import { ApiError, apiFetch } from "@/lib/api";
import { findClient } from "@/lib/clients";
import type { ExecData, ReportData, ReportKind, StaffReport } from "@/lib/portal";
import { lastCompleteMonth } from "@/lib/review";

export const metadata = { title: "Consulting report" };

export default async function ReportPage({ params, searchParams }: { params: Promise<{ clientSlug: string }>; searchParams: Promise<{ month?: string; kind?: string }> }) {
  const { clientSlug } = await params;
  const { month: asked, kind: askedKind } = await searchParams;
  const kind: ReportKind = askedKind === "monthly" ? "monthly" : "executive";
  const client = await findClient(clientSlug);
  if (!client) notFound();
  const month = asked && /^\d{4}-(0[1-9]|1[0-2])$/.test(asked) ? asked : lastCompleteMonth();
  let data: { report: StaffReport; data: ReportData | ExecData } | null = null;
  let error: string | null = null;
  try {
    data = await apiFetch<{ report: StaffReport; data: ReportData | ExecData }>(`/v2/consulting/report?${new URLSearchParams({ month, kind })}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The report could not be loaded: the API did not answer.";
  }
  return <ReportEditor key={`${month}-${kind}`} client={client} month={month} kind={kind} loaded={data} error={error} />;
}
