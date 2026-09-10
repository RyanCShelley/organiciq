import { notFound, redirect } from "next/navigation";

import type { Client } from "@/lib/api";
import {
  accountToolHref,
  RESERVED_ROOT_SLUGS,
  type AccountTool,
} from "@/lib/account-routes";
import { isClientUuid } from "@/lib/client-path";
import { loadClientById, loadClientByParam, resolveClientId, resolveDateRange } from "@/lib/context";

/** Load client for /{slug}/{tool}; redirect UUID params to the slug URL. */
export async function requireAccountClient(
  param: string,
  tool: AccountTool,
  search = "",
): Promise<Client> {
  if (RESERVED_ROOT_SLUGS.has(param)) notFound();
  const client = await loadClientByParam(param);
  if (!client) notFound();
  if (isClientUuid(param) && client.slug !== param) {
    const qs = search.startsWith("?") || search === "" ? search : `?${search}`;
    redirect(`${accountToolHref(client.slug, tool)}${qs}`);
  }
  return client;
}

function preserveAccountQuery(
  params: Record<string, string | string[] | undefined>,
  from: string,
  to: string,
): string {
  const qs = new URLSearchParams();
  if (from) qs.set("from", from);
  if (to) qs.set("to", to);
  for (const key of ["tab", "lever", "range"] as const) {
    const value = params[key];
    if (typeof value === "string" && value) qs.set(key, value);
  }
  const text = qs.toString();
  return text ? `?${text}` : "";
}

/** Redirect legacy /watch-list?clientId=… to /{slug}/watch-list?from&to… */
export async function redirectLegacyAccountTool(
  tool: AccountTool,
  searchParams:
    | Promise<Record<string, string | string[] | undefined>>
    | Record<string, string | string[] | undefined>,
): Promise<never> {
  const params = searchParams instanceof Promise ? await searchParams : searchParams;
  const clientId = await resolveClientId(params);
  const { from, to } = await resolveDateRange(params);
  const client = clientId ? await loadClientById(clientId) : null;
  if (!client) {
    redirect("/clients");
  }
  redirect(`${accountToolHref(client.slug, tool)}${preserveAccountQuery(params, from, to)}`);
}
