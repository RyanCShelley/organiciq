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
