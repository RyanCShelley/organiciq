import { redirectLegacyAccountTool } from "@/lib/account-routes";

export default async function LegacyContentOppRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  await redirectLegacyAccountTool("content-opp", searchParams);
}
