import { MonthlyDashboard } from "@/components/analytics/MonthlyDashboard";
import { previousMonth } from "@/lib/monthly-record";
import { Alert } from "@/components/ui/Alert";
import { apiFetch } from "@/lib/api";
import { requireAccountClient } from "@/lib/account-routes.server";
import { resolveDateRange } from "@/lib/context";
import {
  normalizeDashboardResponse,
  type DashboardResponse,
} from "@/lib/dashboard";

export default async function DashboardPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clientSlug } = await params;
  const client = await requireAccountClient(clientSlug, "dashboard");
  const { from, to } = await resolveDateRange(await searchParams);
  const context = new URLSearchParams({ from, to, range: "custom" });
  const currentMonth = new Date().toISOString().slice(0, 7);
  const reviewMonth =
    to.slice(0, 7) < currentMonth
      ? to.slice(0, 7)
      : previousMonth(currentMonth);
  let data: DashboardResponse | null = null;
  let failure: string | null = null;
  try {
    data = normalizeDashboardResponse(
      await apiFetch<DashboardResponse>(`/dashboard?${context}`, {
        clientId: client.id,
      }),
    );
  } catch (error) {
    failure =
      error instanceof Error ? error.message : "Dashboard could not load";
  }
  if (!data) return <Alert variant="danger">{failure}</Alert>;
  return (
    <MonthlyDashboard
      data={data}
      engineHref={`/${client.slug}/decision-engine?${context}&run=${reviewMonth}`}
      settingsHref={`/clients/${client.slug}?${context}`}
    />
  );
}
