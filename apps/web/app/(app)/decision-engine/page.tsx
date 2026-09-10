import { redirectLegacyAccountTool } from "@/lib/account-routes";

export default async function LegacyDecisionEngineRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  await redirectLegacyAccountTool("decision-engine", searchParams);
}
