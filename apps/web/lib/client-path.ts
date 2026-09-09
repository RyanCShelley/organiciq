import type { Client } from "@/lib/api";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isClientUuid(value: string): boolean {
  return UUID_RE.test(value);
}

/** Public workspace path for a client — uses slug in the URL. */
export function clientHref(client: Pick<Client, "slug"> | string, segment = ""): string {
  const slug = typeof client === "string" ? client : client.slug;
  if (!segment) return `/clients/${slug}`;
  return `/clients/${slug}/${segment}`;
}
