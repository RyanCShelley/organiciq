import {
  AnnotationCreateForm,
  AnnotationImportPanel,
} from "@/components/Annotations/AnnotationForms";
import { AnnotationsTable } from "@/components/Annotations/AnnotationsTable";
import { Alert } from "@/components/ui/Alert";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch } from "@/lib/api";
import { requireAccountClient } from "@/lib/account-routes";
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
      <PageHeader
        title="Annotations"
        description="Causal history for the account — Growth Actions, content, technical changes, and measured impact."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}

      {clientId && !error ? (
        <div className="space-y-[var(--section-gap)]">
          <section className="workspace-section">
            <SectionHeader
              title="Upload history"
              description="Import annotations you’ve already completed so Decision Engine and Dashboard have causal context."
            />
            <div className="workspace-panel">
              <AnnotationImportPanel clientId={clientId} />
            </div>
          </section>

          <section className="workspace-section">
            <SectionHeader
              title="Add annotation"
              description="Log a new change. Set a measurement window to auto-compare pre vs post from GA4/GSC."
            />
            <div className="workspace-panel">
              <AnnotationCreateForm clientId={clientId} />
            </div>
          </section>

          <section className="workspace-section">
            <SectionHeader
              title="Account history"
              description={`${rows.length} annotation${rows.length === 1 ? "" : "s"} with light causal impact (±5% meaningful change).`}
            />
            <div className="workspace-panel">
              <AnnotationsTable rows={rows} />
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
