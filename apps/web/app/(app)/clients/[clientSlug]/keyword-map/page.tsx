import {
  KeywordPageMapTable,
  type KeywordMapRow,
} from "@/components/DecisionEngine/KeywordPageMapTable";
import { ClientWorkspaceNav } from "@/components/ClientWorkspaceNav";
import { Alert } from "@/components/ui/Alert";
import { apiFetch } from "@/lib/api";
import { clientHref } from "@/lib/client-path";
import { requireWorkspaceClient } from "@/lib/context";

type MapPayload = {
  keywords: KeywordMapRow[];
  pages: string[];
};

const EMPTY: MapPayload = { keywords: [], pages: [] };

export default async function KeywordMapPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = await requireWorkspaceClient(clientSlug, "keyword-map");

  let payload: MapPayload = EMPTY;
  let error: string | null = null;
  try {
    payload = await apiFetch<MapPayload>("/decisions/keyword-page-map", {
      clientId: client.id,
    });
  } catch (caught) {
    error = caught instanceof Error ? caught.message : "Could not load the map.";
  }

  return (
    <section>
      <ClientWorkspaceNav
        clientSlug={client.slug}
        active={clientHref(client.slug, "keyword-map")}
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}
      <KeywordPageMapTable
        rows={payload.keywords ?? []}
        pages={payload.pages ?? []}
        clientId={client.id}
        clientSlug={client.slug}
      />
    </section>
  );
}
