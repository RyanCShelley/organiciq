import { redirectLegacyAccountTool } from "@/lib/account-routes";

export default async function LegacyAnnotationsRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  await redirectLegacyAccountTool("annotations", searchParams);
}
