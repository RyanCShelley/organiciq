import type { Client } from "@/lib/api";
import { ACCOUNT_TOOLS } from "@/lib/account-routes";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isClientUuid(value: string): boolean {
  return UUID_RE.test(value);
}

/**
 * Public workspace path for a client — uses slug in the URL: a page in the
 * settings workspace, /clients/{slug}/{segment}.
 *
 * The product tools (dashboard, watch list, content opp, ...) do not live
 * there — they are /{slug}/{tool}. Asking for one used to build
 * /clients/{slug}/dashboard, a path that has never existed, and every
 * sortable table header on the dashboard linked to it. They are sent to
 * their real address instead of 404ing.
 */
export function clientHref(client: Pick<Client, "slug"> | string, segment = ""): string {
  const slug = typeof client === "string" ? client : client.slug;
  if (!segment) return `/clients/${slug}`;
  if ((ACCOUNT_TOOLS as readonly string[]).includes(segment)) return `/${slug}/${segment}`;
  return `/clients/${slug}/${segment}`;
}
