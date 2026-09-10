import { notFound, redirect } from "next/navigation";

import type { Client } from "@/lib/api";
import { isClientUuid } from "@/lib/client-path";
import { loadClientById, loadClientByParam, resolveClientId, resolveDateRange } from "@/lib/context";

export const ACCOUNT_TOOLS = [
  "dashboard",
  "watch-list",
  "content-opp",
  "decision-engine",
  "annotations",
] as const;

export type AccountTool = (typeof ACCOUNT_TOOLS)[number];

/** Path segments that must not be treated as client slugs. */
export const RESERVED_ROOT_SLUGS = new Set<string>([
  ...ACCOUNT_TOOLS,
  "clients",
  "platform",
  "admin",
  "activity",
  "client-strategy",
  "login",
  "api",
  "brand",
  "auth",
]);

export function isAccountTool(value: string): value is AccountTool {
  return (ACCOUNT_TOOLS as readonly string[]).includes(value);
}

/** Account product URL: /{slug}/watch-list */
export function accountToolHref(slug: string, tool: AccountTool | string): string {
  if (!slug) return `/${tool}`;
  return `/${slug}/${tool}`;
}

export function parseAccountToolPath(
  pathname: string,
): { slug: string; tool: AccountTool } | null {
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length < 2) return null;
  const [slug, tool] = parts;
  if (!slug || RESERVED_ROOT_SLUGS.has(slug)) return null;
  if (!isAccountTool(tool)) return null;
  return { slug, tool };
}

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
  searchParams: Promise<Record<string, string | string[] | undefined>> | Record<string, string | string[] | undefined>,
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
