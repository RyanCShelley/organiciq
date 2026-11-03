import { notFound } from "next/navigation";

import { ContentCalendar } from "@/components/ContentCalendar";
import { ApiError, apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import type { CalendarData } from "@/lib/content";

export const metadata = { title: "Content calendar" };

export default async function ContentCalendarPage({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  let data: CalendarData | null = null;
  let error: string | null = null;
  try {
    data = await apiFetch<CalendarData>("/v2/content/calendar", { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The calendar could not be read: the API did not answer.";
  }
  return <ContentCalendar client={client} data={data} error={error} />;
}
