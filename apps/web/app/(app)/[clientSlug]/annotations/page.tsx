import {
  AnnotationCreateForm,
  AnnotationImportPanel,
} from "@/components/Annotations/AnnotationForms";
import { AnnotationsTable } from "@/components/Annotations/AnnotationsTable";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch } from "@/lib/api";
import { requireAccountClient } from "@/lib/account-routes.server";
import type { AnnotationRow } from "@/lib/annotations";

export default async function AnnotationsPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clientSlug } = await params;
  const client = await requireAccountClient(clientSlug, "annotations");
  const clientId = client.id;

  let rows: AnnotationRow[] = [];
  let error: string | null = null;

  try {
    rows = await apiFetch<AnnotationRow[]>("/annotations", { clientId });
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load annotations";
  }

  return (
    <section>
      {error ? <Alert variant="danger">{error}</Alert> : null}

      {clientId && !error ? (
        <div className="space-y-[var(--section-gap)]">
          <section className="workspace-section">
            <SectionHeader title="Completed work" description={`${rows.length} entries. Marking an engine task shipped adds it here. Results describe observed changes, not proof of causation.`} />
            <div className="workspace-panel"><AnnotationsTable rows={rows} clientId={clientId} /></div>
          </section>
          <details className="workspace-section">
            <summary className="cursor-pointer font-semibold">Log completed work</summary>
            <div className="workspace-panel"><AnnotationCreateForm clientId={clientId} /></div>
          </details>
          <details className="workspace-section">
            <summary className="cursor-pointer font-semibold">Import past completed work</summary>
            <div className="workspace-panel"><AnnotationImportPanel clientId={clientId} /></div>
          </details>
        </div>
      ) : null}
    </section>
  );
}
