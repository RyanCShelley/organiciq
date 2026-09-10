import { redirect } from "next/navigation";

import { accountToolHref } from "@/lib/account-routes";
import { requireAccountClient } from "@/lib/account-routes.server";
import { resolveDateRange } from "@/lib/context";

/** /{slug} → /{slug}/dashboard */
export default async function ClientAccountHome({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clientSlug } = await params;
  const query = await searchParams;
  const client = await requireAccountClient(clientSlug, "dashboard");
  const { from, to } = await resolveDateRange(query);
  const qs = new URLSearchParams();
  if (from) qs.set("from", from);
  if (to) qs.set("to", to);
  if (typeof query.range === "string") qs.set("range", query.range);
  const suffix = qs.toString();
  redirect(
    suffix
      ? `${accountToolHref(client.slug, "dashboard")}?${suffix}`
      : accountToolHref(client.slug, "dashboard"),
  );
}
