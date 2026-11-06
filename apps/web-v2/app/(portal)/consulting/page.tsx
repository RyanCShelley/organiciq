import { redirect } from "next/navigation";

import { ApiError } from "@/lib/api";
import { getPortals } from "@/lib/portal";

export const metadata = { title: "Consulting portal" };

export default async function PortalIndex() {
  let slug: string | null = null;
  let error: string | null = null;
  try {
    slug = (await getPortals()).clients[0]?.slug ?? null;
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The portal could not be loaded: the API did not answer.";
  }
  if (slug) redirect(`/consulting/${slug}`);
  return (
    <main className="mx-auto max-w-xl px-6 py-16">
      <h1 className="text-2xl font-bold">Consulting portal</h1>
      <p className="mt-2 text-sm text-[var(--text-secondary)]">{error ?? "No consulting portal is set up for you yet."}</p>
    </main>
  );
}
