import { redirect } from "next/navigation";

/**
 * The map moved to the client workspace.
 *
 * It is a record of what a client's terms mean — set up once and revisited
 * when the watchlist changes — not a tool you open to read a number, so it
 * belongs beside conversions and integrations. This redirect stays for the
 * links and bookmarks that point at the old place.
 */
export default async function LegacyKeywordMapPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  redirect(`/clients/${clientSlug}/keyword-map`);
}
