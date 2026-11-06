import { notFound } from "next/navigation";

import { BriefView } from "@/components/portal/BriefView";
import { ApiError, apiFetch } from "@/lib/api";
import { getPortals, type ClientRec } from "@/lib/portal";

export const metadata = { title: "Recommendation" };

export default async function BriefPage({ params }: { params: Promise<{ clientSlug: string; id: string }> }) {
  const { clientSlug, id } = await params;
  const site = (await getPortals().catch(() => null))?.clients.find((c) => c.slug === clientSlug);
  if (!site) notFound();
  let rec: ClientRec;
  try {
    rec = await apiFetch<ClientRec>(`/v2/consulting/portal/recommendations/${id}`, { clientId: site.id });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  return <BriefView clientId={site.id} slug={site.slug} rec={rec} />;
}
