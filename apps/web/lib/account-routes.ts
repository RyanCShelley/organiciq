export const ACCOUNT_TOOLS = [
  "dashboard",
  "watch-list",
  "content-opp",
  "decision-engine",
  "keyword-map",
  "site-crawl",
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

/**
 * Matches `/{slug}/{tool}` for any account tool.
 *
 * Built from ACCOUNT_TOOLS rather than written out, because it was written
 * out five times — in the sidebar, in nav context, in the workspace params
 * that rewrite the URL when you switch client, and twice more — and adding
 * a tool meant remembering all five. Two were already missing `site-crawl`,
 * which is why the client picker silently stopped switching clients there.
 */
export const ACCOUNT_TOOL_PATH = new RegExp(
  `^/([^/]+)/(${ACCOUNT_TOOLS.join("|")})(/|$)`,
);

/** The tool segment of an account path, or null if it is not one. */
export function accountToolFromPath(pathname: string): AccountTool | null {
  const match = pathname.match(ACCOUNT_TOOL_PATH);
  return match ? (match[2] as AccountTool) : null;
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
