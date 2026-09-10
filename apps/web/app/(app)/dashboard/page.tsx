import { redirectLegacyAccountTool } from "@/lib/account-routes.server";

export default async function LegacyDashboardRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  await redirectLegacyAccountTool("dashboard", searchParams);
}
