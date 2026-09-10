import { redirectLegacyAccountTool } from "@/lib/account-routes.server";

export default async function LegacyContentOppRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  await redirectLegacyAccountTool("content-opp", searchParams);
}
