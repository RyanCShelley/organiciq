import { redirectLegacyAccountTool } from "@/lib/account-routes.server";

export default async function LegacyWatchListRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  await redirectLegacyAccountTool("watch-list", searchParams);
}
